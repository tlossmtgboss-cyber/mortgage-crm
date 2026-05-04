"""
Campaign Reply Handler — routes inbound SMS to campaign conversations.

When a borrower replies to a campaign SMS thread, this handler:
1. Matches the inbound phone to a campaign recipient via message_id
2. Uses Claude Haiku to interpret the reply (schedule, decline, question)
3. Books via AppointmentService if scheduling
4. Updates recipient status
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

llm_haiku = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0,
    max_tokens=256,
)


class CampaignReplyHandler:

    async def handle_inbound(
        self, from_phone: str, message_body: str, org_id: str
    ) -> Optional[Dict[str, Any]]:
        recipient = self._find_campaign_recipient(from_phone)
        if not recipient:
            return None

        intent = await self._classify_reply(message_body)

        if intent["action"] == "schedule":
            return await self._handle_schedule(recipient, intent, org_id)
        elif intent["action"] == "decline":
            return await self._handle_decline(recipient)
        elif intent["action"] == "reschedule":
            return await self._handle_reschedule(recipient, org_id)
        else:
            return await self._handle_clarify(recipient)

    def _find_campaign_recipient(self, phone: str) -> Optional[Dict]:
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT cr.id, cr.campaign_id, cr.lead_id, cr.loan_id, "
                "cr.phone, cr.first_name, cr.status, cr.appointment_id, "
                "ac.created_by_user_id, ac.organization_id "
                "FROM aria_campaign_recipients cr "
                "JOIN aria_campaigns ac ON cr.campaign_id = ac.id "
                "WHERE cr.phone = :phone AND cr.status IN ('sent', 'delivered', 'replied') "
                "ORDER BY cr.sent_at DESC LIMIT 1"
            ), {"phone": phone}).fetchone()

            if not row:
                return None

            return {
                "id": row[0], "campaign_id": row[1], "lead_id": row[2],
                "loan_id": row[3], "phone": row[4], "first_name": row[5],
                "status": row[6], "appointment_id": row[7],
                "lo_user_id": row[8], "organization_id": row[9],
            }
        finally:
            db.close()

    async def _classify_reply(self, message: str) -> Dict[str, Any]:
        response = await llm_haiku.ainvoke([
            SystemMessage(content=(
                "Classify this SMS reply to a mortgage outreach. "
                "Respond ONLY with JSON: "
                '{"action": "schedule|decline|reschedule|clarify", '
                '"datetime_mentioned": "ISO datetime or null", '
                '"raw_time": "the time phrase they used or null"}'
            )),
            HumanMessage(content=message),
        ])

        try:
            return json.loads(response.content.strip())
        except json.JSONDecodeError:
            return {"action": "clarify", "datetime_mentioned": None}

    async def _handle_schedule(
        self, recipient: Dict, intent: Dict, org_id: str
    ) -> Dict:
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from dateutil import parser as dtparser

        dt_str = intent.get("datetime_mentioned")
        if not dt_str:
            return {
                "action": "ask_time",
                "phone": recipient["phone"],
                "response": f"Great, {recipient['first_name'] or 'there'}! What day and time works best for you?",
            }

        scheduled_start = dtparser.parse(dt_str)

        db = SessionLocal()
        try:
            svc = AppointmentService(
                db=db, organization_id=recipient["organization_id"]
            )
            result = await svc.create_appointment(
                data={
                    "title": f"Call — {recipient['first_name'] or 'Borrower'}",
                    "scheduled_start": scheduled_start.isoformat(),
                    "duration_minutes": 30,
                    "assigned_user_id": recipient["lo_user_id"],
                    "attendee_phone": recipient["phone"],
                    "attendee_name": recipient["first_name"] or "",
                    "meeting_type": "consultation",
                    "meeting_mode": "phone",
                },
                source="aria_campaign",
                requester_user_id=recipient["lo_user_id"],
            )
            db.commit()

            appointment_id = (
                getattr(result, "appointment_id", None)
                or (result.get("appointment_id") if isinstance(result, dict) else None)
            )

            self._update_recipient_status(
                recipient["id"], "booked", appointment_id=appointment_id
            )
            self._increment_campaign_counter(recipient["campaign_id"], "booked_count")

            return {
                "action": "booked",
                "phone": recipient["phone"],
                "appointment_id": appointment_id,
                "response": (
                    f"You're set for {scheduled_start.strftime('%A at %I:%M %p')}! "
                    f"Calendar invite on the way."
                ),
            }
        except Exception as e:
            db.rollback()
            logger.error("Campaign booking failed: %s", e)
            return {
                "action": "booking_failed",
                "phone": recipient["phone"],
                "response": "I had trouble booking that time. Could you try a different time?",
            }
        finally:
            db.close()

    async def _handle_decline(self, recipient: Dict) -> Dict:
        self._update_recipient_status(recipient["id"], "declined")
        self._increment_campaign_counter(recipient["campaign_id"], "declined_count")
        return {
            "action": "declined",
            "phone": recipient["phone"],
            "response": "No problem at all. Take care!",
        }

    async def _handle_reschedule(self, recipient: Dict, org_id: str) -> Dict:
        from aria.tools.communication_tools import CommunicationTools
        comms = CommunicationTools()

        schedule = await comms.get_schedule(
            lo_id=recipient["lo_user_id"],
            org_id=str(recipient["organization_id"]),
        )
        slots = schedule.get("available_slots", [])[:3]

        if not slots:
            return {
                "action": "no_slots",
                "phone": recipient["phone"],
                "response": "Let me check with the team and get back to you with some times.",
            }

        slot_text = ", ".join(
            f"{s.get('day', '')} {s.get('start', '')}" for s in slots
        )
        return {
            "action": "propose_slots",
            "phone": recipient["phone"],
            "response": f"How about {slot_text}?",
        }

    async def _handle_clarify(self, recipient: Dict) -> Dict:
        return {
            "action": "clarify",
            "phone": recipient["phone"],
            "response": (
                "Would you like to pick a time for a quick call, "
                "or would you prefer we reach out another way?"
            ),
        }

    def _update_recipient_status(
        self, recipient_id: int, status: str, appointment_id: int = None
    ):
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            params: dict = {"id": recipient_id, "status": status}
            extra = ""
            if status == "booked" and appointment_id:
                extra = ", appointment_id = :apt_id, booked_at = NOW()"
                params["apt_id"] = appointment_id
            elif status == "replied":
                extra = ", replied_at = NOW()"

            db.execute(text(
                f"UPDATE aria_campaign_recipients SET status = :status{extra} WHERE id = :id"
            ), params)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to update recipient status: %s", e)
        finally:
            db.close()

    def _increment_campaign_counter(self, campaign_id: int, counter: str):
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(text(
                f"UPDATE aria_campaigns SET {counter} = {counter} + 1 WHERE id = :id"
            ), {"id": campaign_id})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to increment campaign counter: %s", e)
        finally:
            db.close()
