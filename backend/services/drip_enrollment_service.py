"""Drip enrollment service — enroll, pause, resume, switch sequences for leads.

Uses persistent database storage (drip_enrollments / drip_enrollment_events tables)
instead of in-memory dicts. Survives deployments and restarts.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from sqlalchemy import and_
from sqlalchemy.orm import Session

from services.drip_campaign_templates import get_template, list_templates

logger = logging.getLogger(__name__)


def _ensure_tables():
    """Create drip enrollment tables if they don't exist (production-safe)."""
    try:
        from db import engine
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent
        DripEnrollment.__table__.create(engine, checkfirst=True)
        DripEnrollmentEvent.__table__.create(engine, checkfirst=True)
        logger.info("drip_enrollments / drip_enrollment_events tables ensured")
    except Exception as e:
        logger.warning(f"Could not ensure drip enrollment tables: {e}")


def _enrollment_to_dict(enrollment) -> Dict:
    """Convert a DripEnrollment ORM instance to a JSON-safe dict."""
    return {
        "enrollment_id": enrollment.id,
        "lead_id": enrollment.lead_id,
        "sequence_name": enrollment.sequence_name,
        "sequence_id": enrollment.sequence_id,
        "status": enrollment.status,
        "current_step_index": enrollment.current_step_index,
        "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
        "paused_at": enrollment.paused_at.isoformat() if enrollment.paused_at else None,
        "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
        "next_step_at": enrollment.next_step_at.isoformat() if enrollment.next_step_at else None,
        "exit_reason": enrollment.exit_reason,
    }


def _compute_next_step_at(template: Dict, step_index: int) -> Optional[datetime]:
    """Calculate when the next step should fire based on template step definitions."""
    all_steps = []
    for phase in template.get("phases", []):
        all_steps.extend(phase.get("steps", []))
    if step_index >= len(all_steps):
        return None
    step = all_steps[step_index]
    day_offset = step.get("day", 0)
    delay_min = step.get("delay_min", 0)
    return datetime.now(timezone.utc) + timedelta(days=day_offset, minutes=delay_min)


def _count_total_steps(template: Dict) -> int:
    """Count total steps across all phases."""
    return sum(len(p.get("steps", [])) for p in template.get("phases", []))


class DripEnrollmentService:
    """Manages lead enrollment in drip sequences with persistent DB storage."""

    def enroll_lead(self, db: Session, lead_id: str, sequence_name: str,
                    org_id: str) -> Dict:
        """Enroll a lead in a drip sequence."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        # Verify template exists
        template = get_template(sequence_name)
        if not template:
            raise ValueError(
                f"Unknown sequence: {sequence_name}. "
                f"Available: {[t['key'] for t in list_templates()]}"
            )

        lead_id_int = int(lead_id)
        org_id_int = int(org_id)

        # Check for existing active enrollment in same sequence
        existing = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.sequence_name == sequence_name,
                DripEnrollment.status.in_(["active", "paused"]),
            )
        ).first()

        if existing:
            return {"status": "already_enrolled", "enrollment": _enrollment_to_dict(existing)}

        # Check opt-out status before enrolling
        if not self._check_opt_out(db, lead_id_int, org_id_int):
            return {"status": "blocked", "reason": "Lead has opted out of communications"}

        # Compute initial next_step_at
        next_step = _compute_next_step_at(template, 0)

        # Create enrollment record
        enrollment = DripEnrollment(
            organization_id=org_id_int,
            lead_id=lead_id_int,
            sequence_name=sequence_name,
            status="active",
            current_step_index=0,
            enrolled_at=datetime.now(timezone.utc),
            next_step_at=next_step,
        )
        db.add(enrollment)
        db.flush()  # get enrollment.id

        # Record enrollment event
        event = DripEnrollmentEvent(
            enrollment_id=enrollment.id,
            event_type="enrolled",
            step_index=0,
            detail=f"Enrolled in sequence '{sequence_name}'",
        )
        db.add(event)
        db.commit()
        db.refresh(enrollment)

        logger.info(
            f"Enrolled lead {lead_id} in sequence '{sequence_name}' "
            f"(enrollment {enrollment.id}, org {org_id})"
        )

        return {
            "status": "enrolled",
            "enrollment": _enrollment_to_dict(enrollment),
            "sequence": {
                "name": template["name"],
                "total_phases": len(template.get("phases", [])),
                "total_steps": _count_total_steps(template),
            },
        }

    def pause_enrollment(self, db: Session, lead_id: str, reason: str = "") -> Dict:
        """Pause all active drip sequences for a lead."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)
        now = datetime.now(timezone.utc)

        active_enrollments = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status == "active",
            )
        ).all()

        paused = 0
        for enrollment in active_enrollments:
            enrollment.status = "paused"
            enrollment.paused_at = now
            enrollment.extra_metadata = {
                **(enrollment.extra_metadata or {}),
                "pause_reason": reason,
            }

            event = DripEnrollmentEvent(
                enrollment_id=enrollment.id,
                event_type="paused",
                step_index=enrollment.current_step_index,
                detail=reason or "Paused by user",
            )
            db.add(event)
            paused += 1

        if paused:
            db.commit()

        return {"status": "paused", "paused_count": paused, "reason": reason}

    def resume_enrollment(self, db: Session, lead_id: str) -> Dict:
        """Resume paused drip sequences."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)

        paused_enrollments = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status == "paused",
            )
        ).all()

        resumed = 0
        now = datetime.now(timezone.utc)
        for enrollment in paused_enrollments:
            enrollment.status = "active"
            enrollment.paused_at = None

            # Recalculate next_step_at from current position
            template = get_template(enrollment.sequence_name)
            if template:
                enrollment.next_step_at = _compute_next_step_at(
                    template, enrollment.current_step_index
                )

            event = DripEnrollmentEvent(
                enrollment_id=enrollment.id,
                event_type="resumed",
                step_index=enrollment.current_step_index,
                detail="Resumed by user",
            )
            db.add(event)
            resumed += 1

        if resumed:
            db.commit()

        return {"status": "resumed", "resumed_count": resumed}

    def switch_sequence(self, db: Session, lead_id: str, new_sequence: str,
                        org_id: str, reason: str = "") -> Dict:
        """Cancel current sequences and enroll in a new one."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)
        now = datetime.now(timezone.utc)

        # Cancel all active/paused enrollments
        active = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status.in_(["active", "paused"]),
            )
        ).all()

        switched_from = len(active)
        for enrollment in active:
            enrollment.status = "cancelled"
            enrollment.exit_reason = f"Switched to '{new_sequence}': {reason}"
            enrollment.completed_at = now

            event = DripEnrollmentEvent(
                enrollment_id=enrollment.id,
                event_type="switched",
                step_index=enrollment.current_step_index,
                detail=f"Switched to '{new_sequence}': {reason}",
            )
            db.add(event)

        if active:
            db.commit()

        # Enroll in new sequence
        result = self.enroll_lead(db, lead_id, new_sequence, org_id)
        result["switched_from"] = switched_from
        result["reason"] = reason
        return result

    def get_active_enrollments(self, db: Session, lead_id: str) -> List[Dict]:
        """Get all active/paused drip enrollments for a lead."""
        from database.models.drip_enrollment import DripEnrollment

        lead_id_int = int(lead_id)
        enrollments = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.status.in_(["active", "paused"]),
            )
        ).all()

        return [_enrollment_to_dict(e) for e in enrollments]

    def get_all_enrollments(self, db: Session, lead_id: str) -> List[Dict]:
        """Get all enrollments (any status) for a lead."""
        from database.models.drip_enrollment import DripEnrollment

        lead_id_int = int(lead_id)
        enrollments = db.query(DripEnrollment).filter(
            DripEnrollment.lead_id == lead_id_int,
        ).order_by(DripEnrollment.enrolled_at.desc()).all()

        return [_enrollment_to_dict(e) for e in enrollments]

    def process_due_steps(self, db: Session) -> List[Dict]:
        """Find enrollments where next_step_at <= now() and execute the next step.

        Called by a periodic scheduler (e.g. cron / background task).
        Returns a list of step execution results.
        """
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        now = datetime.now(timezone.utc)
        results = []

        due_enrollments = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.status == "active",
                DripEnrollment.next_step_at != None,  # noqa: E711
                DripEnrollment.next_step_at <= now,
            )
        ).limit(200).all()

        for enrollment in due_enrollments:
            try:
                template = get_template(enrollment.sequence_name)
                if not template:
                    logger.warning(
                        f"Enrollment {enrollment.id}: template '{enrollment.sequence_name}' not found, skipping"
                    )
                    continue

                # Gather all steps across phases
                all_steps = []
                for phase in template.get("phases", []):
                    all_steps.extend(phase.get("steps", []))

                step_index = enrollment.current_step_index
                if step_index >= len(all_steps):
                    # Sequence complete
                    enrollment.status = "completed"
                    enrollment.completed_at = now
                    enrollment.next_step_at = None

                    event = DripEnrollmentEvent(
                        enrollment_id=enrollment.id,
                        event_type="completed",
                        step_index=step_index,
                        detail="All steps completed",
                    )
                    db.add(event)
                    results.append({
                        "enrollment_id": enrollment.id,
                        "action": "completed",
                        "lead_id": enrollment.lead_id,
                    })
                    continue

                step = all_steps[step_index]
                channel = step.get("channel", "email")

                # Check opt-out before sending
                if not self._check_opt_out(db, enrollment.lead_id, enrollment.organization_id):
                    enrollment.status = "exited"
                    enrollment.exit_reason = "Lead opted out"
                    enrollment.completed_at = now
                    enrollment.next_step_at = None

                    event = DripEnrollmentEvent(
                        enrollment_id=enrollment.id,
                        event_type="exited",
                        step_index=step_index,
                        detail="Lead opted out of communications",
                    )
                    db.add(event)
                    results.append({
                        "enrollment_id": enrollment.id,
                        "action": "exited_opt_out",
                        "lead_id": enrollment.lead_id,
                    })
                    continue

                # Record step sent event (actual delivery delegated to channel services)
                event = DripEnrollmentEvent(
                    enrollment_id=enrollment.id,
                    event_type="step_sent",
                    step_index=step_index,
                    channel=channel,
                    detail=f"Step {step_index}: {channel} - {step.get('template', 'custom')}",
                )
                db.add(event)

                # Advance to next step
                next_index = step_index + 1
                enrollment.current_step_index = next_index

                if next_index >= len(all_steps):
                    # That was the last step
                    enrollment.status = "completed"
                    enrollment.completed_at = now
                    enrollment.next_step_at = None
                else:
                    # Schedule next step based on day offset difference
                    next_day = all_steps[next_index].get("day", 0)
                    current_day = step.get("day", 0)
                    day_delta = max(next_day - current_day, 1)
                    enrollment.next_step_at = now + timedelta(days=day_delta)

                results.append({
                    "enrollment_id": enrollment.id,
                    "action": "step_sent",
                    "lead_id": enrollment.lead_id,
                    "step_index": step_index,
                    "channel": channel,
                    "template": step.get("template"),
                })

            except Exception as e:
                logger.exception(
                    f"Error processing due step for enrollment {enrollment.id}: {e}"
                )
                results.append({
                    "enrollment_id": enrollment.id,
                    "action": "error",
                    "error": str(e),
                })

        if due_enrollments:
            try:
                db.commit()
            except Exception as e:
                logger.exception(f"Failed to commit due step processing: {e}")
                db.rollback()

        return results

    def _check_opt_out(self, db: Session, lead_id: int, org_id: int) -> bool:
        """Check if lead has opted out of communications."""
        try:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead or not lead.phone:
                return True  # Can't check, allow enrollment

            # SMSOptOut lives in models/sms_models.py, not database/models/
            from models.sms_models import SMSOptOut
            opt_out = db.query(SMSOptOut).filter(
                SMSOptOut.phone_number == lead.phone,
                SMSOptOut.organization_id == org_id,
                SMSOptOut.active == True,  # noqa: E712
            ).first()
            return opt_out is None
        except Exception as e:
            logger.debug(f"Could not check opt-out status, allowing enrollment: {e}")
            return True


# Module-level singleton
_service: Optional[DripEnrollmentService] = None
_tables_ensured = False


def get_drip_enrollment_service() -> DripEnrollmentService:
    global _service, _tables_ensured
    if not _tables_ensured:
        _ensure_tables()
        _tables_ensured = True
    if _service is None:
        _service = DripEnrollmentService()
    return _service
