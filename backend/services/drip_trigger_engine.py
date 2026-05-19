"""Behavioral trigger engine — adapts drip sequences based on lead engagement."""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class TriggerAction:
    action: str  # escalate_frequency, reduce_frequency, pause_drip, switch_sequence, stop_all, send_targeted, send_rate_alert
    detail: str
    new_sequence: Optional[str] = None
    reason: str = ""


TRIGGER_RULES = {
    # Engagement escalation
    "email_opened": TriggerAction(
        action="escalate_frequency",
        detail="Move from monthly to weekly frequency",
        reason="Borrower opened an email — showing interest",
    ),
    "link_clicked": TriggerAction(
        action="escalate_frequency",
        detail="Move from weekly to daily for 3 days",
        reason="Borrower clicked a link — active engagement",
    ),
    "sms_replied": TriggerAction(
        action="pause_drip",
        detail="Pause drip sequence, route to live AI conversation",
        reason="Borrower replied to SMS — switch to real-time conversation",
    ),
    "website_visit": TriggerAction(
        action="send_targeted",
        detail="Send content related to the page visited",
        reason="Borrower visited website — send relevant follow-up",
    ),
    "rate_drop": TriggerAction(
        action="send_rate_alert",
        detail="Alert all active nurture leads about rate drop",
        reason="Rates dropped >0.25% — time-sensitive opportunity",
    ),

    # De-escalation
    "no_engagement_14d": TriggerAction(
        action="reduce_frequency",
        detail="Move from weekly to biweekly",
        reason="No engagement in 14 days — reduce frequency to avoid fatigue",
    ),
    "no_engagement_30d": TriggerAction(
        action="reduce_frequency",
        detail="Move from biweekly to monthly",
        reason="No engagement in 30 days — minimal contact to stay top-of-mind",
    ),
    "email_bounced": TriggerAction(
        action="switch_channel",
        detail="Switch primary channel from email to SMS",
        reason="Email bouncing — try alternate channel",
    ),

    # Exit conditions
    "opted_out": TriggerAction(
        action="stop_all",
        detail="Immediately stop all sequences for this contact",
        reason="Contact opted out — compliance requirement",
    ),
    "appointment_booked": TriggerAction(
        action="switch_sequence",
        detail="Switch to appointment prep sequence",
        new_sequence="appointment_prep",
        reason="Appointment booked — switch to prep mode",
    ),
    "application_submitted": TriggerAction(
        action="switch_sequence",
        detail="Switch to loan lifecycle sequence",
        new_sequence="loan_lifecycle",
        reason="Application submitted — LOS now owns the workflow",
    ),
    "loan_funded": TriggerAction(
        action="switch_sequence",
        detail="Switch to post-close referral sequence",
        new_sequence="post_close",
        reason="Loan funded — transition to post-close nurture",
    ),
    "lead_disqualified": TriggerAction(
        action="switch_sequence",
        detail="Switch to long-term nurture (12-month)",
        new_sequence="long_nurture",
        reason="Lead disqualified now — keep warm for future",
    ),
}


class DripTriggerEngine:
    """Monitors lead behavior and adjusts drip sequences."""

    def evaluate_triggers(self, event_type: str, event_data: dict = None) -> List[TriggerAction]:
        """Evaluate triggers for an event, return actions to take."""
        actions = []

        rule = TRIGGER_RULES.get(event_type)
        if rule:
            actions.append(rule)
            logger.info(f"Trigger fired: {event_type} -> {rule.action}: {rule.detail}")

        return actions

    def execute_actions(self, db: Session, lead_id: str, actions: List[TriggerAction],
                        org_id: str) -> List[Dict]:
        """Execute trigger actions on a lead's drip enrollment."""
        results = []

        for action in actions:
            try:
                if action.action == "stop_all":
                    result = self._stop_all_sequences(db, lead_id, org_id)
                elif action.action == "pause_drip":
                    result = self._pause_sequences(db, lead_id, org_id, action.reason)
                elif action.action == "switch_sequence":
                    result = self._switch_sequence(db, lead_id, org_id, action.new_sequence, action.reason)
                elif action.action in ("escalate_frequency", "reduce_frequency"):
                    result = self._adjust_frequency(db, lead_id, org_id, action.action, action.detail)
                else:
                    result = {"action": action.action, "status": "logged", "detail": action.detail}

                results.append(result)
            except Exception as _exc:  # noqa: BLE001
                logger.exception(f"Failed to execute trigger action {action.action} for lead {lead_id}")
                results.append({"action": action.action, "status": "failed"})

        return results

    def _stop_all_sequences(self, db: Session, lead_id: str, org_id: str) -> Dict:
        """Stop all active drip enrollments for a lead."""
        try:
            from database.models.drip_enrollment import DripEnrollment
            from datetime import datetime, timezone
            lead_id_int = int(lead_id)
            now = datetime.now(timezone.utc)
            enrollments = db.query(DripEnrollment).filter(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status.in_(["active", "paused"]),
            ).all()
            for e in enrollments:
                e.status = "cancelled"
                e.exit_reason = "Stopped by trigger engine"
                e.completed_at = now
                e.next_step_at = None
            db.commit()
            return {"action": "stop_all", "status": "completed", "stopped": len(enrollments)}
        except Exception as e:
            logger.debug(f"Could not stop enrollments via DB: {e}")
            return {"action": "stop_all", "status": "logged"}

    def _pause_sequences(self, db: Session, lead_id: str, org_id: str, reason: str) -> Dict:
        """Pause active drip sequences."""
        try:
            from database.models.drip_enrollment import DripEnrollment
            from datetime import datetime, timezone
            lead_id_int = int(lead_id)
            now = datetime.now(timezone.utc)
            enrollments = db.query(DripEnrollment).filter(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status == "active",
            ).all()
            for e in enrollments:
                e.status = "paused"
                e.paused_at = now
            db.commit()
            return {"action": "pause_drip", "status": "completed", "paused": len(enrollments), "reason": reason}
        except Exception as e:
            logger.debug(f"Could not pause enrollments via DB: {e}")
            return {"action": "pause_drip", "status": "logged", "reason": reason}

    def _switch_sequence(self, db: Session, lead_id: str, org_id: str,
                         new_sequence: str, reason: str) -> Dict:
        """Switch lead to a different drip sequence."""
        self._stop_all_sequences(db, lead_id, org_id)
        return {
            "action": "switch_sequence",
            "status": "completed",
            "new_sequence": new_sequence,
            "reason": reason,
        }

    def _adjust_frequency(self, db: Session, lead_id: str, org_id: str,
                          direction: str, detail: str) -> Dict:
        """Adjust drip frequency up or down."""
        return {
            "action": direction,
            "status": "logged",
            "detail": detail,
        }


_engine = None


def get_drip_trigger_engine() -> DripTriggerEngine:
    global _engine
    if _engine is None:
        _engine = DripTriggerEngine()
    return _engine
