"""
Graduated reminder cadence for campaign-booked appointments.

- Day before: "Reminder: you have a call with [LO] tomorrow at [time]"
- 1 hour before: "Your call with [LO] is in 1 hour"
- No-show (15 min after missed): "We missed you — want to reschedule?"
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


class CampaignReminderService:

    async def check_and_send_reminders(self) -> Dict[str, int]:
        from aria.tools.communication_tools import CommunicationTools
        comms = CommunicationTools()

        now = datetime.now(timezone.utc)
        counts = {"day_before": 0, "hour_before": 0, "no_show": 0}

        day_before_recipients = self._get_due_reminders("day_before", now)
        for r in day_before_recipients:
            msg = (
                f"Reminder: you have a call with {r['lo_name']} "
                f"tomorrow at {r['appointment_time']}."
            )
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "reminder_day_before_sent")
                counts["day_before"] += 1
            except Exception as e:
                logger.error("Day-before reminder failed for %s: %s", r["phone"], e)

        hour_before_recipients = self._get_due_reminders("hour_before", now)
        for r in hour_before_recipients:
            msg = f"Your call with {r['lo_name']} is in 1 hour."
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "reminder_hour_before_sent")
                counts["hour_before"] += 1
            except Exception as e:
                logger.error("Hour-before reminder failed for %s: %s", r["phone"], e)

        no_show_recipients = self._get_due_reminders("no_show", now)
        for r in no_show_recipients:
            msg = (
                f"We missed you today — want to reschedule? "
                f"Reply with a time that works."
            )
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "no_show_followup_sent")
                self._update_recipient_status(r["recipient_id"], "no_show")
                counts["no_show"] += 1
            except Exception as e:
                logger.error("No-show follow-up failed for %s: %s", r["phone"], e)

        return counts

    def _get_due_reminders(self, reminder_type: str, now: datetime) -> List[Dict]:
        db = SessionLocal()
        try:
            if reminder_type == "day_before":
                window_start = now + timedelta(hours=23)
                window_end = now + timedelta(hours=25)
                flag_col = "reminder_day_before_sent"
            elif reminder_type == "hour_before":
                window_start = now + timedelta(minutes=55)
                window_end = now + timedelta(minutes=65)
                flag_col = "reminder_hour_before_sent"
            elif reminder_type == "no_show":
                window_start = now - timedelta(minutes=30)
                window_end = now - timedelta(minutes=15)
                flag_col = "no_show_followup_sent"
            else:
                return []

            rows = db.execute(text(f"""
                SELECT cr.id, cr.phone, cr.first_name,
                       sa.scheduled_start, sa.assigned_user_id,
                       ac.organization_id,
                       u.first_name || ' ' || u.last_name as lo_name
                FROM aria_campaign_recipients cr
                JOIN scheduler_appointments sa ON cr.appointment_id = sa.id
                JOIN aria_campaigns ac ON cr.campaign_id = ac.id
                LEFT JOIN users u ON sa.assigned_user_id = u.id
                WHERE cr.status = 'booked'
                AND cr.{flag_col} = false
                AND sa.scheduled_start BETWEEN :ws AND :we
                AND sa.status = 'booked'
            """), {"ws": window_start, "we": window_end}).fetchall()

            return [
                {
                    "recipient_id": r[0],
                    "phone": r[1],
                    "first_name": r[2],
                    "appointment_time": r[3].strftime("%I:%M %p") if r[3] else "",
                    "lo_user_id": r[4],
                    "organization_id": r[5],
                    "lo_name": r[6] or "your loan officer",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Failed to fetch %s reminders: %s", reminder_type, e)
            return []
        finally:
            db.close()

    def _mark_reminder_sent(self, recipient_id: int, flag: str):
        db = SessionLocal()
        try:
            db.execute(text(
                f"UPDATE aria_campaign_recipients SET {flag} = true WHERE id = :id"
            ), {"id": recipient_id})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to mark reminder sent: %s", e)
        finally:
            db.close()

    def _update_recipient_status(self, recipient_id: int, status: str):
        db = SessionLocal()
        try:
            db.execute(text(
                "UPDATE aria_campaign_recipients SET status = :status WHERE id = :id"
            ), {"id": recipient_id, "status": status})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to update recipient status: %s", e)
        finally:
            db.close()
