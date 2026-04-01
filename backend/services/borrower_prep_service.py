"""Borrower prep sequence service — pre-appointment document and reminder sequences."""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from database.models.borrower_prep import BorrowerPrepSequence, BorrowerPrepStep

logger = logging.getLogger(__name__)

APPOINTMENT_PREP_CONFIGS = {
    "pre_approval_consult": {
        "display_name": "Pre-Approval Consultation",
        "required_docs": [
            {"name": "2 years of W-2s", "category": "income", "priority": "required"},
            {"name": "Most recent 30 days of pay stubs", "category": "income", "priority": "required"},
            {"name": "2 months of bank statements (all pages)", "category": "assets", "priority": "required"},
            {"name": "Government-issued photo ID", "category": "identity", "priority": "required"},
            {"name": "Social Security Number", "category": "identity", "priority": "required"},
            {"name": "Most recent tax returns (if self-employed)", "category": "income", "priority": "conditional"},
        ],
        "prep_timeline": [
            {"trigger": "T-48h", "hours_before": 48, "channel": "email", "template_key": "prep_email_full",
             "content": None},  # Generated dynamically
            {"trigger": "T-24h", "hours_before": 24, "channel": "sms", "template_key": "reminder_24h",
             "content": "Hi {first_name}, your consultation with {lo_name} is tomorrow at {time}. Have your W-2s, pay stubs, and bank statements ready. Questions? Reply here!"},
            {"trigger": "T-2h", "hours_before": 2, "channel": "sms", "template_key": "reminder_2h",
             "content": "Your call with {lo_name} is in 2 hours at {time}. Quick reminder to have your documents handy. We'll walk through everything together!"},
            {"trigger": "T-30m", "hours_before": 0.5, "channel": "sms", "template_key": "final_reminder",
             "content": "Almost time! {lo_name} will be calling you in 30 minutes. Looking forward to getting you pre-approved!"},
        ],
    },
    "rate_lock_call": {
        "display_name": "Rate Lock Discussion",
        "required_docs": [
            {"name": "Current loan estimate", "category": "loan_docs", "priority": "required"},
            {"name": "Rate lock preference (float vs lock)", "category": "decision", "priority": "required"},
        ],
        "prep_timeline": [
            {"trigger": "T-24h", "hours_before": 24, "channel": "email", "template_key": "rate_lock_prep",
             "content": None},
            {"trigger": "T-1h", "hours_before": 1, "channel": "sms", "template_key": "rate_lock_reminder",
             "content": "Hi {first_name}, {lo_name} will call in 1 hour to discuss locking your rate. Have your loan estimate handy!"},
        ],
    },
    "closing_prep": {
        "display_name": "Closing Preparation",
        "required_docs": [
            {"name": "Cashier's check for closing costs", "category": "closing", "priority": "required"},
            {"name": "Government-issued photo ID (2 forms)", "category": "identity", "priority": "required"},
            {"name": "Signed closing disclosure", "category": "closing", "priority": "required"},
            {"name": "Proof of homeowners insurance", "category": "property", "priority": "required"},
        ],
        "prep_timeline": [
            {"trigger": "T-72h", "hours_before": 72, "channel": "email", "template_key": "closing_prep_full",
             "content": None},
            {"trigger": "T-48h", "hours_before": 48, "channel": "sms", "template_key": "closing_48h",
             "content": "Your closing is in 2 days! Make sure you have your cashier's check and two forms of ID. Questions? Text me!"},
            {"trigger": "T-24h", "hours_before": 24, "channel": "email", "template_key": "closing_24h",
             "content": None},
            {"trigger": "T-2h", "hours_before": 2, "channel": "sms", "template_key": "closing_day",
             "content": "Today's the day, {first_name}! Head to your closing location at {time}. Bring your IDs and cashier's check. Congrats on your new home!"},
        ],
    },
}


class BorrowerPrepService:
    """Creates and manages pre-appointment preparation sequences."""

    def create_prep_sequence(self, db: Session, appointment_id: str, appointment_type: str,
                             lead_data: dict, lo_data: dict, appointment_time: datetime,
                             org_id: str) -> Dict:
        """Create a prep sequence with scheduled steps."""
        config = APPOINTMENT_PREP_CONFIGS.get(appointment_type)
        if not config:
            raise ValueError(f"Unknown appointment type: {appointment_type}")

        # Create sequence
        sequence = BorrowerPrepSequence(
            appointment_id=appointment_id,
            lead_id=lead_data.get("id"),
            organization_id=org_id,
            appointment_type=appointment_type,
        )
        db.add(sequence)
        db.flush()

        # Create steps
        variables = {
            "first_name": lead_data.get("first_name", ""),
            "lo_name": lo_data.get("name", ""),
            "time": appointment_time.strftime("%I:%M %p"),
            "date": appointment_time.strftime("%m/%d/%Y"),
        }

        steps_created = []
        for step_config in config["prep_timeline"]:
            hours_before = step_config["hours_before"]
            trigger_time = appointment_time - timedelta(hours=hours_before)

            # Skip if trigger time already passed
            if trigger_time <= datetime.utcnow():
                continue

            content = step_config.get("content")
            if content:
                content = self._render_variables(content, variables)

            step = BorrowerPrepStep(
                sequence_id=sequence.id,
                trigger_offset=step_config["trigger"],
                trigger_time=trigger_time,
                channel=step_config["channel"],
                template_key=step_config["template_key"],
                content=content,
            )
            db.add(step)
            steps_created.append({
                "trigger": step_config["trigger"],
                "channel": step_config["channel"],
                "trigger_time": trigger_time.isoformat(),
                "template": step_config["template_key"],
            })

        db.commit()

        return {
            "sequence_id": sequence.id,
            "appointment_id": appointment_id,
            "appointment_type": appointment_type,
            "display_name": config["display_name"],
            "steps_created": len(steps_created),
            "steps": steps_created,
            "required_docs": config["required_docs"],
        }

    def get_sequence_status(self, db: Session, appointment_id: str) -> Optional[Dict]:
        """Get status of prep sequence and all steps."""
        sequence = db.query(BorrowerPrepSequence).filter(
            BorrowerPrepSequence.appointment_id == appointment_id,
        ).first()

        if not sequence:
            return None

        steps = db.query(BorrowerPrepStep).filter(
            BorrowerPrepStep.sequence_id == sequence.id,
        ).order_by(BorrowerPrepStep.trigger_time).all()

        return {
            "sequence_id": sequence.id,
            "appointment_id": sequence.appointment_id,
            "appointment_type": sequence.appointment_type,
            "status": sequence.status,
            "steps": [
                {
                    "id": s.id,
                    "trigger": s.trigger_offset,
                    "channel": s.channel,
                    "template": s.template_key,
                    "status": s.status,
                    "trigger_time": s.trigger_time.isoformat() if s.trigger_time else None,
                    "sent_at": s.sent_at.isoformat() if s.sent_at else None,
                }
                for s in steps
            ],
            "sent_count": len([s for s in steps if s.status == "sent"]),
            "pending_count": len([s for s in steps if s.status == "scheduled"]),
        }

    def send_prep_step(self, db: Session, step_id: str) -> Dict:
        """Execute a single prep step (send SMS or email)."""
        step = db.query(BorrowerPrepStep).filter(BorrowerPrepStep.id == step_id).first()
        if not step:
            raise ValueError(f"Step {step_id} not found")

        if step.status != "scheduled":
            return {"status": "skipped", "reason": f"Step already {step.status}"}

        try:
            if step.channel == "sms" and step.content:
                logger.info(f"Sending prep SMS for step {step_id}: {step.content[:50]}...")
                # Integration point: call SMS service here
                step.status = "sent"
                step.sent_at = datetime.utcnow()
            elif step.channel == "email":
                logger.info(f"Sending prep email for step {step_id}: {step.template_key}")
                # Integration point: call email composer here
                step.status = "sent"
                step.sent_at = datetime.utcnow()
            else:
                step.status = "failed"
                logger.warning(f"No content or unknown channel for step {step_id}")

            db.commit()
            return {"status": step.status, "step_id": step_id, "channel": step.channel}

        except Exception as e:
            step.status = "failed"
            db.commit()
            logger.exception(f"Failed to send prep step {step_id}")
            return {"status": "failed", "error": str(e)}

    def check_document_readiness(self, db: Session, lead_id: str, appointment_type: str) -> Dict:
        """Check which required documents the borrower has already uploaded."""
        config = APPOINTMENT_PREP_CONFIGS.get(appointment_type, {})
        required = config.get("required_docs", [])

        # Check documents table
        try:
            from database.models.document import Document
            existing_docs = db.query(Document).filter(
                Document.lead_id == lead_id,
                Document.status == "active",
            ).all()
            existing_types = {d.doc_type for d in existing_docs} if existing_docs else set()
        except Exception:
            existing_types = set()

        readiness = []
        for doc in required:
            doc_key = doc["name"].lower().replace(" ", "_")[:30]
            is_uploaded = any(doc_key in (et or "").lower() for et in existing_types)
            readiness.append({
                "document": doc["name"],
                "category": doc["category"],
                "priority": doc["priority"],
                "uploaded": is_uploaded,
            })

        uploaded_count = len([r for r in readiness if r["uploaded"]])
        required_count = len([r for r in readiness if r["priority"] == "required"])
        required_uploaded = len([r for r in readiness if r["uploaded"] and r["priority"] == "required"])

        return {
            "lead_id": lead_id,
            "appointment_type": appointment_type,
            "total_required": required_count,
            "uploaded": uploaded_count,
            "required_uploaded": required_uploaded,
            "ready": required_uploaded >= required_count,
            "documents": readiness,
        }

    def cancel_prep_sequence(self, db: Session, appointment_id: str) -> Dict:
        """Cancel all pending steps for an appointment."""
        sequence = db.query(BorrowerPrepSequence).filter(
            BorrowerPrepSequence.appointment_id == appointment_id,
        ).first()

        if not sequence:
            return {"cancelled": 0, "message": "No prep sequence found"}

        pending_steps = db.query(BorrowerPrepStep).filter(
            BorrowerPrepStep.sequence_id == sequence.id,
            BorrowerPrepStep.status == "scheduled",
        ).all()

        for step in pending_steps:
            step.status = "cancelled"

        sequence.status = "cancelled"
        db.commit()

        return {"cancelled": len(pending_steps), "sequence_id": sequence.id}

    def _render_variables(self, template: str, variables: dict) -> str:
        for key, value in variables.items():
            template = template.replace("{" + key + "}", str(value or ""))
        return template


_service = None


def get_borrower_prep_service() -> BorrowerPrepService:
    global _service
    if _service is None:
        _service = BorrowerPrepService()
    return _service
