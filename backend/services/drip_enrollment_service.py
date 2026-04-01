"""Drip enrollment service — enroll, pause, resume, switch sequences for leads."""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from services.drip_campaign_templates import get_template, list_templates

logger = logging.getLogger(__name__)


class DripEnrollment:
    """In-memory enrollment record (use database model when available)."""
    def __init__(self, lead_id: str, sequence_name: str, org_id: str):
        self.id = str(uuid.uuid4())[:12].upper()
        self.lead_id = lead_id
        self.sequence_name = sequence_name
        self.organization_id = org_id
        self.status = "active"  # active, paused, completed, stopped
        self.current_phase = 0
        self.current_step = 0
        self.paused_reason = None
        self.started_at = datetime.utcnow()
        self.paused_at = None

    def to_dict(self) -> Dict:
        return {
            "enrollment_id": self.id,
            "lead_id": self.lead_id,
            "sequence_name": self.sequence_name,
            "status": self.status,
            "current_phase": self.current_phase,
            "current_step": self.current_step,
            "started_at": self.started_at.isoformat(),
        }


class DripEnrollmentService:
    """Manages lead enrollment in drip sequences."""

    def __init__(self):
        # In-memory store until DripEnrollment model is available
        self._enrollments: Dict[str, List[DripEnrollment]] = {}

    def enroll_lead(self, db: Session, lead_id: str, sequence_name: str,
                    org_id: str) -> Dict:
        """Enroll a lead in a drip sequence."""
        # Verify template exists
        template = get_template(sequence_name)
        if not template:
            raise ValueError(f"Unknown sequence: {sequence_name}. Available: {[t['key'] for t in list_templates()]}")

        # Check for existing active enrollment
        existing = self.get_active_enrollments(lead_id)
        for e in existing:
            if e.sequence_name == sequence_name and e.status == "active":
                return {"status": "already_enrolled", "enrollment": e.to_dict()}

        # Check opt-out status before enrolling
        opt_out_clear = self._check_opt_out(db, lead_id, org_id)
        if not opt_out_clear:
            return {"status": "blocked", "reason": "Lead has opted out of communications"}

        # Create enrollment
        enrollment = DripEnrollment(lead_id, sequence_name, org_id)
        self._enrollments.setdefault(lead_id, []).append(enrollment)

        logger.info(f"Enrolled lead {lead_id} in sequence '{sequence_name}' (enrollment {enrollment.id})")

        return {
            "status": "enrolled",
            "enrollment": enrollment.to_dict(),
            "sequence": {
                "name": template["name"],
                "total_phases": len(template.get("phases", [])),
                "total_steps": sum(len(p.get("steps", [])) for p in template.get("phases", [])),
            },
        }

    def pause_enrollment(self, lead_id: str, reason: str = "") -> Dict:
        """Pause all active drip sequences for a lead."""
        enrollments = self.get_active_enrollments(lead_id)
        paused = 0
        for e in enrollments:
            if e.status == "active":
                e.status = "paused"
                e.paused_reason = reason
                e.paused_at = datetime.utcnow()
                paused += 1

        return {"status": "paused", "paused_count": paused, "reason": reason}

    def resume_enrollment(self, lead_id: str) -> Dict:
        """Resume paused drip sequences."""
        enrollments = self._enrollments.get(lead_id, [])
        resumed = 0
        for e in enrollments:
            if e.status == "paused":
                e.status = "active"
                e.paused_at = None
                e.paused_reason = None
                resumed += 1

        return {"status": "resumed", "resumed_count": resumed}

    def switch_sequence(self, db: Session, lead_id: str, new_sequence: str,
                        org_id: str, reason: str = "") -> Dict:
        """Stop current sequences and enroll in a new one."""
        # Stop all active
        enrollments = self.get_active_enrollments(lead_id)
        for e in enrollments:
            e.status = "stopped"

        # Enroll in new
        result = self.enroll_lead(db, lead_id, new_sequence, org_id)
        result["switched_from"] = len(enrollments)
        result["reason"] = reason
        return result

    def get_active_enrollments(self, lead_id: str) -> List[DripEnrollment]:
        """Get all active drip enrollments for a lead."""
        return [
            e for e in self._enrollments.get(lead_id, [])
            if e.status in ("active", "paused")
        ]

    def get_all_enrollments(self, lead_id: str) -> List[Dict]:
        """Get all enrollments (any status) for a lead."""
        return [e.to_dict() for e in self._enrollments.get(lead_id, [])]

    def _check_opt_out(self, db: Session, lead_id: str, org_id: str) -> bool:
        """Check if lead has opted out of communications."""
        try:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead or not lead.phone:
                return True  # Can't check, allow enrollment

            from database.models.communication import SMSOptOut
            opt_out = db.query(SMSOptOut).filter(
                SMSOptOut.phone_number == lead.phone,
                SMSOptOut.organization_id == org_id,
                SMSOptOut.active == True,
            ).first()
            return opt_out is None
        except Exception:
            logger.debug("Could not check opt-out status, allowing enrollment")
            return True


_service = None


def get_drip_enrollment_service() -> DripEnrollmentService:
    global _service
    if _service is None:
        _service = DripEnrollmentService()
    return _service
