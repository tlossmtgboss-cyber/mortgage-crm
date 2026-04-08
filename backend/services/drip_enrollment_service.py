"""Drip enrollment service — enroll, pause, resume, switch sequences for leads.

Uses persistent database storage (drip_enrollments / drip_enrollment_events tables)
instead of in-memory dicts. Survives deployments and restarts.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo

from sqlalchemy import and_
from sqlalchemy.orm import Session

from services.drip_campaign_templates import get_template, list_templates

logger = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "America/New_York"


def _ensure_tables():
    """Create drip enrollment tables if they don't exist (production-safe)."""
    try:
        from db import engine
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent
        DripEnrollment.__table__.create(engine, checkfirst=True)
        DripEnrollmentEvent.__table__.create(engine, checkfirst=True)
        logger.info("drip_enrollments / drip_enrollment_events tables ensured")
    except Exception as e:
        logger.warning("Could not ensure drip enrollment tables: %s", e)


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


def _compute_next_step_at(
    template: Dict,
    step_index: int,
    timezone_str: Optional[str] = None,
) -> Optional[datetime]:
    """Calculate when the next step should fire based on template step definitions.

    If *timezone_str* is provided the step is scheduled relative to the
    borrower's local clock (e.g. "Day 1, 10 am Eastern") and then
    converted back to UTC for storage.  Falls back to America/New_York
    when no timezone is supplied.
    """
    all_steps = []
    for phase in template.get("phases", []):
        all_steps.extend(phase.get("steps", []))
    if step_index >= len(all_steps):
        return None
    step = all_steps[step_index]
    day_offset = step.get("day", 0)
    delay_min = step.get("delay_min", 0)

    try:
        tz = ZoneInfo(timezone_str) if timezone_str else ZoneInfo(_DEFAULT_TIMEZONE)
    except (KeyError, Exception):
        tz = ZoneInfo(_DEFAULT_TIMEZONE)

    # Compute the target time in the borrower's local timezone, then convert to UTC
    local_now = datetime.now(tz)
    local_target = local_now + timedelta(days=day_offset, minutes=delay_min)
    return local_target.astimezone(timezone.utc)


def _count_total_steps(template: Dict) -> int:
    """Count total steps across all phases."""
    return sum(len(p.get("steps", [])) for p in template.get("phases", []))


class DripEnrollmentService:
    """Manages lead enrollment in drip sequences with persistent DB storage."""

    def enroll_lead(self, db: Session, lead_id: str, sequence_name: str,
                    org_id: str, timezone_str: Optional[str] = None) -> Dict:
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
        _extra = {"lead_id": lead_id_int, "organization_id": org_id_int}

        # Check for existing active enrollment in same sequence
        existing = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.organization_id == org_id_int,
                DripEnrollment.lead_id == lead_id_int,
                DripEnrollment.sequence_name == sequence_name,
                DripEnrollment.status.in_(["active", "paused"]),
            )
        ).first()

        if existing:
            logger.info(
                "Lead already enrolled in sequence '%s'",
                sequence_name,
                extra={**_extra, "enrollment_id": existing.id},
            )
            return {"status": "already_enrolled", "enrollment": _enrollment_to_dict(existing)}

        # Check opt-out status before enrolling
        if not self._check_opt_out(db, lead_id_int, org_id_int):
            logger.info(
                "Enrollment blocked — lead opted out",
                extra=_extra,
            )
            return {"status": "blocked", "reason": "Lead has opted out of communications"}

        # Compute initial next_step_at (timezone-aware)
        next_step = _compute_next_step_at(template, 0, timezone_str=timezone_str)

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

        # Record enrollment event with consent basis for TCPA audit trail
        event = DripEnrollmentEvent(
            enrollment_id=enrollment.id,
            event_type="enrolled",
            step_index=0,
            detail=(
                f"Enrolled in sequence '{sequence_name}'. "
                f"Consent basis: opt-out check passed at {datetime.now(timezone.utc).isoformat()}"
            ),
        )
        db.add(event)
        db.commit()
        db.refresh(enrollment)

        logger.info(
            "Enrolled lead in sequence '%s'",
            sequence_name,
            extra={**_extra, "enrollment_id": enrollment.id},
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

    def pause_enrollment(self, db: Session, lead_id: str, reason: str = "",
                         org_id: str = "") -> Dict:
        """Pause all active drip sequences for a lead within an organization."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)
        org_id_int = int(org_id) if org_id else None
        now = datetime.now(timezone.utc)
        _extra = {"lead_id": lead_id_int, "organization_id": org_id_int}

        filters = [
            DripEnrollment.lead_id == lead_id_int,
            DripEnrollment.status == "active",
        ]
        if org_id_int:
            filters.append(DripEnrollment.organization_id == org_id_int)

        active_enrollments = db.query(DripEnrollment).filter(
            and_(*filters)
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
            logger.info(
                "Paused enrollment %s",
                enrollment.id,
                extra={**_extra, "enrollment_id": enrollment.id},
            )
            paused += 1

        if paused:
            db.commit()

        return {"status": "paused", "paused_count": paused, "reason": reason}

    def resume_enrollment(self, db: Session, lead_id: str, org_id: str = "",
                          timezone_str: Optional[str] = None) -> Dict:
        """Resume paused drip sequences within an organization."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)
        org_id_int = int(org_id) if org_id else None
        _extra = {"lead_id": lead_id_int, "organization_id": org_id_int}

        filters = [
            DripEnrollment.lead_id == lead_id_int,
            DripEnrollment.status == "paused",
        ]
        if org_id_int:
            filters.append(DripEnrollment.organization_id == org_id_int)

        paused_enrollments = db.query(DripEnrollment).filter(
            and_(*filters)
        ).all()

        resumed = 0
        now = datetime.now(timezone.utc)
        for enrollment in paused_enrollments:
            enrollment.status = "active"
            enrollment.paused_at = None

            # Recalculate next_step_at from current position (timezone-aware)
            template = get_template(enrollment.sequence_name)
            if template:
                enrollment.next_step_at = _compute_next_step_at(
                    template, enrollment.current_step_index,
                    timezone_str=timezone_str,
                )

            event = DripEnrollmentEvent(
                enrollment_id=enrollment.id,
                event_type="resumed",
                step_index=enrollment.current_step_index,
                detail=f"Resumed by user at step {enrollment.current_step_index}",
            )
            db.add(event)
            logger.info(
                "Resumed enrollment %s at step %s",
                enrollment.id,
                enrollment.current_step_index,
                extra={**_extra, "enrollment_id": enrollment.id},
            )
            resumed += 1

        if resumed:
            db.commit()

        return {"status": "resumed", "resumed_count": resumed}

    def switch_sequence(self, db: Session, lead_id: str, new_sequence: str,
                        org_id: str, reason: str = "",
                        timezone_str: Optional[str] = None) -> Dict:
        """Cancel current sequences and enroll in a new one."""
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent

        lead_id_int = int(lead_id)
        org_id_int = int(org_id)
        now = datetime.now(timezone.utc)
        _extra = {"lead_id": lead_id_int, "organization_id": org_id_int}

        # Cancel all active/paused enrollments within this org
        active = db.query(DripEnrollment).filter(
            and_(
                DripEnrollment.organization_id == org_id_int,
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
            logger.info(
                "Cancelled enrollment %s for sequence switch to '%s'",
                enrollment.id,
                new_sequence,
                extra={**_extra, "enrollment_id": enrollment.id},
            )

        # Validate new template BEFORE committing cancellations (atomic switch)
        template = get_template(new_sequence)
        if not template:
            db.rollback()
            raise ValueError(
                f"Unknown sequence: {new_sequence}. "
                f"Available: {[t['key'] for t in list_templates()]}"
            )

        # Don't commit cancellations separately — let enroll_lead commit everything atomically
        # enroll_lead calls db.commit() which will include both the cancellations and the new enrollment
        result = self.enroll_lead(db, lead_id, new_sequence, org_id,
                                  timezone_str=timezone_str)
        result["switched_from"] = switched_from
        result["reason"] = reason
        return result

    def get_active_enrollments(self, db: Session, lead_id: str,
                               org_id: str = "") -> List[Dict]:
        """Get all active/paused drip enrollments for a lead within an organization."""
        from database.models.drip_enrollment import DripEnrollment

        lead_id_int = int(lead_id)
        filters = [
            DripEnrollment.lead_id == lead_id_int,
            DripEnrollment.status.in_(["active", "paused"]),
        ]
        if org_id:
            filters.append(DripEnrollment.organization_id == int(org_id))

        enrollments = db.query(DripEnrollment).filter(
            and_(*filters)
        ).all()

        return [_enrollment_to_dict(e) for e in enrollments]

    def get_all_enrollments(self, db: Session, lead_id: str,
                            org_id: str = "",
                            limit: int = 50,
                            offset: int = 0) -> tuple:
        """Get enrollments (any status) for a lead within an organization (paginated).

        Returns (list_of_dicts, total_count).
        """
        from database.models.drip_enrollment import DripEnrollment
        from sqlalchemy import func

        lead_id_int = int(lead_id)
        filters = [DripEnrollment.lead_id == lead_id_int]
        if org_id:
            filters.append(DripEnrollment.organization_id == int(org_id))

        base_q = db.query(DripEnrollment).filter(and_(*filters))
        total_count = base_q.with_entities(func.count(DripEnrollment.id)).scalar()

        enrollments = (
            base_q
            .order_by(DripEnrollment.enrolled_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [_enrollment_to_dict(e) for e in enrollments], total_count

    def process_due_steps(self, db: Session, org_id: Optional[int] = None) -> List[Dict]:
        """Find enrollments where next_step_at <= now() and execute the next step.

        Called by a periodic scheduler (e.g. cron / background task).
        If org_id is provided, only process enrollments for that organization.
        Returns a list of step execution results.

        Uses a JOIN to avoid N+1 queries and processes in batches of 50.
        """
        from database.models.drip_enrollment import DripEnrollment, DripEnrollmentEvent
        from database.models.lead_loan import Lead

        now = datetime.now(timezone.utc)
        results = []
        _BATCH_SIZE = 50

        filters = [
            DripEnrollment.status == "active",
            DripEnrollment.next_step_at != None,  # noqa: E711
            DripEnrollment.next_step_at <= now,
        ]
        if org_id is not None:
            filters.append(DripEnrollment.organization_id == org_id)

        # PERF-001: Single query with JOIN to leads table — validates FK integrity
        # and allows the DB to filter out orphaned enrollments in one round-trip.
        # Note: joinedload is NOT used here because FOR UPDATE + eager-load
        # can cause locking issues on the joined table in PostgreSQL.
        due_enrollments = (
            db.query(DripEnrollment)
            .join(Lead, and_(Lead.id == DripEnrollment.lead_id,
                             Lead.organization_id == DripEnrollment.organization_id))
            .filter(and_(*filters))
            .with_for_update(skip_locked=True)
            .limit(200)
            .all()
        )

        # Pre-load lead data in a single batch query to avoid per-enrollment lookups
        lead_ids = list({e.lead_id for e in due_enrollments})
        lead_map: Dict[int, Lead] = {}
        if lead_ids:
            leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
            lead_map = {l.id: l for l in leads}

        # Process in batches of 50
        for batch_start in range(0, len(due_enrollments), _BATCH_SIZE):
            batch = due_enrollments[batch_start:batch_start + _BATCH_SIZE]

            for enrollment in batch:
                _extra = {
                    "enrollment_id": enrollment.id,
                    "lead_id": enrollment.lead_id,
                    "organization_id": enrollment.organization_id,
                }
                try:
                    template = get_template(enrollment.sequence_name)
                    if not template:
                        logger.warning(
                            "Template '%s' not found, skipping enrollment",
                            enrollment.sequence_name,
                            extra=_extra,
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
                        logger.info("Enrollment completed — all steps done", extra=_extra)
                        results.append({
                            "enrollment_id": enrollment.id,
                            "action": "completed",
                            "lead_id": enrollment.lead_id,
                        })
                        continue

                    step = all_steps[step_index]
                    channel = step.get("channel", "email")

                    # Check opt-out before sending (uses pre-loaded lead data)
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
                        logger.info("Enrollment exited — lead opted out", extra=_extra)
                        results.append({
                            "enrollment_id": enrollment.id,
                            "action": "exited_opt_out",
                            "lead_id": enrollment.lead_id,
                        })
                        continue

                    # Record step as ready for dispatch (actual delivery delegated to channel services)
                    # WARNING: delivery is NOT performed here — channel services must pick up this event
                    event = DripEnrollmentEvent(
                        enrollment_id=enrollment.id,
                        event_type="step_ready",
                        step_index=step_index,
                        channel=channel,
                        detail=f"Step {step_index}: {channel} - {step.get('template', 'custom')} (pending dispatch)",
                    )
                    db.add(event)
                    logger.info(
                        "Drip step ready for dispatch: step=%s channel=%s",
                        step_index,
                        channel,
                        extra=_extra,
                    )

                    # Advance to next step
                    next_index = step_index + 1
                    enrollment.current_step_index = next_index

                    # DATA-006: Record step_advanced event for audit trail completeness
                    advance_event = DripEnrollmentEvent(
                        enrollment_id=enrollment.id,
                        event_type="step_advanced",
                        step_index=next_index,
                        detail=f"Advanced from step {step_index} to {next_index}",
                    )
                    db.add(advance_event)

                    if next_index >= len(all_steps):
                        # That was the last step
                        enrollment.status = "completed"
                        enrollment.completed_at = now
                        enrollment.next_step_at = None
                        logger.info(
                            "Enrollment completed after final step %s",
                            step_index,
                            extra=_extra,
                        )
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
                        "Error processing due step for enrollment: %s",
                        e,
                        extra=_extra,
                    )
                    results.append({
                        "enrollment_id": enrollment.id,
                        "action": "error",
                        "error": str(e),
                    })

            # Commit after each batch to avoid holding locks too long
            try:
                db.commit()
            except Exception as e:
                logger.exception(
                    "Failed to commit batch starting at offset %s: %s",
                    batch_start,
                    e,
                    extra={"organization_id": org_id},
                )
                db.rollback()

        return results

    def _check_opt_out(self, db: Session, lead_id: int, org_id: int) -> bool:
        """Check if lead has opted out of communications."""
        _extra = {"lead_id": lead_id, "organization_id": org_id}
        try:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.organization_id == org_id).first()
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
            logger.warning(
                "Could not check opt-out status (allowing enrollment as fallback): %s",
                e,
                extra=_extra,
            )
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
