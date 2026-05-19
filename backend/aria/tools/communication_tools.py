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
        """Book a real appointment on the LO's calendar, sync to Outlook, and send invite."""
        try:
            from db import SessionLocal
            from services.appointment.service import AppointmentService
            from dateutil import parser as dtparser

            org_id = lo.get("organization_id", "")
            contact_name = with_contact.get("name", "")
            title = f"Call — {contact_name}" + (f" — {topic}" if topic else "")
            scheduled_start = dtparser.parse(f"{date} {time}")

            db = SessionLocal()
            try:
                svc = AppointmentService(db=db, organization_id=int(org_id) if org_id else None)
                result = await svc.create_appointment(
                    data={
                        "title": title,
                        "scheduled_start": scheduled_start.isoformat(),
                        "duration_minutes": duration_minutes,
                        "assigned_user_id": int(lo["id"]),
                        "attendee_email": with_contact.get("email", ""),
                        "attendee_name": contact_name,
                        "attendee_phone": with_contact.get("phone", ""),
                        "meeting_type": "consultation",
                        "meeting_mode": "phone",
                        "description": topic or f"Scheduled call with {contact_name}",
                    },
                    source="ai_scheduler",
                    requester_user_id=int(lo["id"]),
                )
                db.commit()
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                db.rollback()
                raise
            finally:
                db.close()

            appointment_id = getattr(result, "appointment_id", None) or (result.get("appointment_id") if isinstance(result, dict) else None)
            outlook_link = getattr(result, "outlook_web_link", None) or (result.get("outlook_web_link") if isinstance(result, dict) else None)

            sms_sent = False
            contact_phone = with_contact.get("phone")
            if contact_phone:
                try:
                    lo_name = lo.get("full_name", "your loan officer")
                    sms_body = (
                        f"Hi {contact_name}, you have a call scheduled with {lo_name}"
                        f" on {date} at {time}"
                        + (f" regarding {topic}" if topic else "")
                        + ". A calendar invite has been sent to your email."
                        + f" — {lo_name}"
                    )
                    await self.send_sms(
                        to_phone=contact_phone,
                        from_user=lo,
                        message=sms_body,
                        org_id=str(org_id),
                    )
                    sms_sent = True
                except Exception as sms_err:
                    logger.warning(f"Could not send confirmation SMS to {contact_phone}: {sms_err}")

            return {
                "datetime": f"{date} {time}",
                "duration_minutes": duration_minutes,
                "with": contact_name,
                "appointment_id": appointment_id,
                "calendar_link": outlook_link,
                "outlook_synced": bool(outlook_link),
                "invite_sent": bool(with_contact.get("email")),
                "sms_sent": sms_sent,
                "note": "Appointment booked, calendar invite sent." + (" SMS confirmation sent." if sms_sent else ""),
            }
        except Exception as e:
            logger.error(f"Aria schedule call failed: {e}", exc_info=True)
            raise ValueError(f"Failed to schedule call: {e}")

    async def get_schedule(
        self, lo_id: int, org_id: str,
        date_from: str = None, date_to: str = None,
        duration_minutes: int = 30,
    ) -> Dict:
        """Check the LO's calendar: upcoming appointments and available slots."""
        try:
            from db import SessionLocal
            from services.appointment.service import AppointmentService
            from datetime import date as date_type, timedelta
            from dateutil import parser as dtparser

            if date_from:
                start = dtparser.parse(date_from).date()
            else:
                start = date_type.today()

            if date_to:
                end = dtparser.parse(date_to).date()
            else:
                end = start + timedelta(days=3)

            db = SessionLocal()
            try:
                svc = AppointmentService(db=db, organization_id=int(org_id) if org_id else None)

                upcoming = []
                try:
                    upcoming_raw = await svc.list_appointments(
                        user_id=lo_id,
                        start_date=start,
                        end_date=end,
                        status="booked",
                        limit=20,
                    )
                    for apt in (upcoming_raw.get("items", []) if isinstance(upcoming_raw, dict) else []):
                        upcoming.append({
                            "id": apt.get("id"),
                            "title": apt.get("title", ""),
                            "start": str(apt.get("scheduled_start", "")),
                            "end": str(apt.get("scheduled_end", "")),
                            "attendee": apt.get("attendee_name", ""),
                            "type": apt.get("meeting_type", ""),
                            "status": apt.get("status", ""),
                        })
                except Exception as e:
                    logger.warning(f"Could not fetch upcoming appointments: {e}")

                available = []
                try:
                    slots_raw = await svc.get_available_slots(
                        lo_id=lo_id,
                        start_date=start,
                        end_date=end,
                        duration_minutes=duration_minutes,
                    )
                    for slot in (slots_raw or [])[:10]:
                        available.append({
                            "start": str(slot.get("start", "")),
                            "end": str(slot.get("end", "")),
                            "date": str(slot.get("date", "")),
                            "day": slot.get("day", ""),
                        })
                except Exception as e:
                    logger.warning(f"Could not fetch available slots: {e}")
            finally:
                db.close()

            return {
                "date_range": f"{start} to {end}",
                "upcoming_count": len(upcoming),
                "upcoming": upcoming,
                "available_slots_count": len(available),
                "available_slots": available,
            }
        except Exception as e:
            logger.error(f"Aria calendar check failed: {e}", exc_info=True)
            raise ValueError(f"Failed to check calendar: {e}")

    async def send_batch_sms(
        self, recipients: list, from_user: Dict,
        message_template: str, org_id: str,
    ) -> list:
        """Send SMS to multiple recipients. Returns list of results."""
        results = []
        for recipient in recipients:
            try:
                result = await self.send_sms(
                    to_phone=recipient["phone"],
                    from_user=from_user,
                    message=message_template.replace(
                        "[first_name]",
                        recipient.get("first_name", "there"),
                    ),
                    org_id=org_id,
                )
                results.append({**result, "phone": recipient["phone"]})
            except Exception as e:
                results.append({
                    "phone": recipient["phone"],
                    "status": "failed",
                    "error": str(e),
                })
        return results

    async def send_reminder(
        self, to_phone: str, from_user: Dict,
        message: str, org_id: str,
    ) -> Dict:
        """Send a reminder SMS (thin wrapper around send_sms for clarity)."""
        return await self.send_sms(
            to_phone=to_phone,
            from_user=from_user,
            message=message,
            org_id=org_id,
        )
