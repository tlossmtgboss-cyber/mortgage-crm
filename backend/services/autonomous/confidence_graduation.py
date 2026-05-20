"""
Confidence Graduation Service

The missing "watch → learn → graduate" loop for autonomous agent execution.

Flow:
1. Autonomous agents propose actions → AgentAction(requires_approval=True)
2. Humans approve/reject via the UI
3. This service records each decision and recalculates confidence
4. When confidence exceeds the threshold (0.950) with sufficient sample size,
   the action type graduates → future actions skip human approval
5. If post-graduation failures occur, confidence is revoked

Integrates with:
- AutonomousTaskExecutor (task_executor.py) — called after each execution
- AgentAction model — reads approval outcomes
- ActionTypeConfidence model — persists graduation state
- WorkflowSLAService — uses AI_AUTO_EXECUTE_THRESHOLD constant
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Graduation thresholds
AUTO_EXECUTE_THRESHOLD = Decimal("0.950")  # 95% approval rate
MIN_SAMPLE_SIZE = 20  # Minimum decisions before graduation is possible
REVOCATION_FAILURE_RATE = Decimal("0.10")  # >10% post-graduation failures → revoke
REVOCATION_WINDOW = 50  # Check last N auto-executed actions for failure rate


class ConfidenceGraduationService:
    """
    Manages the confidence lifecycle for autonomous agent action types.

    Usage:
        service = ConfidenceGraduationService(db)

        # After a human approves an action:
        service.record_decision(org_id, "send_sms", approved=True)

        # Check if an action type should require approval:
        needs_approval = service.requires_approval(org_id, "send_sms")

        # Run periodic graduation check:
        service.evaluate_graduations(org_id)
    """

    def __init__(self, db: Session):
        self.db = db
        self._load_models()

    def _load_models(self):
        """Lazy-load models to avoid circular imports."""
        from database.models.action_type_confidence import ActionTypeConfidence
        from database.models.autonomous_task import AgentAction
        self.ActionTypeConfidence = ActionTypeConfidence
        self.AgentAction = AgentAction

    def record_decision(
        self,
        org_id: int,
        action_type: str,
        approved: bool,
    ) -> Dict[str, Any]:
        """
        Record a human approval/rejection decision and recalculate confidence.

        Args:
            org_id: Organization ID
            action_type: The action type (send_sms, send_email, create_task, etc.)
            approved: True if human approved, False if rejected

        Returns:
            Updated confidence state
        """
        record = self._get_or_create(org_id, action_type)

        record.total_proposed = (record.total_proposed or 0) + 1
        if approved:
            record.total_approved = (record.total_approved or 0) + 1
        else:
            record.total_rejected = (record.total_rejected or 0) + 1

        # Recalculate confidence score using exponential moving average
        # Recent decisions weigh more heavily
        record.confidence_score = self._calculate_confidence(record)
        record.updated_at = datetime.now(timezone.utc)

        self.db.flush()

        # Check for graduation before building result
        newly_graduated = False
        if not record.is_graduated and self._should_graduate(record):
            self._graduate(record)
            newly_graduated = True
            logger.info(
                "Action type '%s' graduated for org %d (confidence=%.4f, decisions=%d)",
                action_type, org_id, record.confidence_score, record.total_decisions,
            )

        result = {
            "org_id": org_id,
            "action_type": action_type,
            "decision": "approved" if approved else "rejected",
            "confidence_score": float(record.confidence_score),
            "total_decisions": record.total_decisions,
            "is_graduated": record.is_graduated,
        }
        if newly_graduated:
            result["graduated"] = True

        return result

    def record_auto_execution(
        self,
        org_id: int,
        action_type: str,
        success: bool,
    ) -> None:
        """
        Record an auto-executed action outcome (post-graduation).
        Used to detect post-graduation failures that warrant revocation.
        """
        record = self._get_or_create(org_id, action_type)
        record.total_auto_executed = (record.total_auto_executed or 0) + 1
        record.updated_at = datetime.now(timezone.utc)

        if not success and record.is_graduated:
            # Check if we should revoke graduation
            if self._should_revoke(record):
                self._revoke(record)
                logger.warning(
                    "Revoked graduation for '%s' org %d — post-graduation failure rate too high",
                    action_type, org_id,
                )

        self.db.flush()

    def requires_approval(self, org_id: int, action_type: str) -> bool:
        """
        Check whether an action type still requires human approval.

        Returns True (require approval) if:
        - No confidence record exists yet
        - The action type hasn't graduated
        - Graduation was revoked
        """
        record = (
            self.db.query(self.ActionTypeConfidence)
            .filter_by(organization_id=org_id, action_type=action_type)
            .first()
        )
        if record is None:
            return True
        return not record.is_graduated

    def evaluate_graduations(self, org_id: int) -> List[Dict[str, Any]]:
        """
        Periodic check: evaluate all action types for an org and graduate
        any that meet the threshold.

        Returns list of newly graduated action types.
        """
        records = (
            self.db.query(self.ActionTypeConfidence)
            .filter_by(organization_id=org_id, is_graduated=False)
            .all()
        )

        graduated = []
        for record in records:
            # Recalculate confidence from current data
            record.confidence_score = self._calculate_confidence(record)
            if self._should_graduate(record):
                self._graduate(record)
                graduated.append({
                    "action_type": record.action_type,
                    "confidence_score": float(record.confidence_score),
                    "total_decisions": record.total_decisions,
                })

        if graduated:
            self.db.flush()
            logger.info(
                "Graduated %d action types for org %d: %s",
                len(graduated), org_id,
                ", ".join(g["action_type"] for g in graduated),
            )

        return graduated

    def get_confidence_dashboard(self, org_id: int) -> Dict[str, Any]:
        """Get confidence status for all action types in an org."""
        records = (
            self.db.query(self.ActionTypeConfidence)
            .filter_by(organization_id=org_id)
            .order_by(self.ActionTypeConfidence.confidence_score.desc())
            .all()
        )

        return {
            "org_id": org_id,
            "action_types": [
                {
                    "action_type": r.action_type,
                    "confidence_score": float(r.confidence_score),
                    "total_proposed": r.total_proposed,
                    "total_approved": r.total_approved,
                    "total_rejected": r.total_rejected,
                    "total_auto_executed": r.total_auto_executed,
                    "approval_rate": round(r.approval_rate, 4),
                    "is_graduated": r.is_graduated,
                    "graduated_at": r.graduated_at.isoformat() if r.graduated_at else None,
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                }
                for r in records
            ],
            "graduated_count": sum(1 for r in records if r.is_graduated),
            "total_tracked": len(records),
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_or_create(self, org_id: int, action_type: str):
        """Get or create an ActionTypeConfidence record.

        Handles concurrent INSERT race: if flush raises IntegrityError
        (unique constraint violation), roll back and re-fetch.
        """
        record = (
            self.db.query(self.ActionTypeConfidence)
            .filter_by(organization_id=org_id, action_type=action_type)
            .first()
        )
        if record is None:
            record = self.ActionTypeConfidence(
                organization_id=org_id,
                action_type=action_type,
                confidence_score=Decimal("0.0"),
                total_proposed=0,
                total_approved=0,
                total_rejected=0,
                total_auto_executed=0,
                is_graduated=False,
            )
            self.db.add(record)
            try:
                self.db.flush()
            except Exception:
                self.db.rollback()
                record = (
                    self.db.query(self.ActionTypeConfidence)
                    .filter_by(organization_id=org_id, action_type=action_type)
                    .first()
                )
                if record is None:
                    raise
        return record

    def _calculate_confidence(self, record) -> Decimal:
        """
        Calculate confidence score using weighted approval rate.

        Formula: exponential moving average that weights recent decisions more.
        With a minimum floor based on sample size.
        """
        total = record.total_decisions
        if total == 0:
            return Decimal("0.0")

        # Base: simple approval rate
        approval_rate = Decimal(str(record.approval_rate))

        # Sample size penalty: confidence can't exceed a ceiling until enough
        # decisions have been made. This prevents graduating after 3/3 approvals.
        sample_factor = min(Decimal("1.0"), Decimal(str(total)) / Decimal(str(MIN_SAMPLE_SIZE)))

        # Effective confidence = approval_rate * sample_factor
        confidence = approval_rate * sample_factor

        return min(Decimal("1.0"), confidence.quantize(Decimal("0.0001")))

    def _should_graduate(self, record) -> bool:
        """Check if an action type should graduate to auto-execute."""
        if record.is_graduated:
            return False
        if record.total_decisions < MIN_SAMPLE_SIZE:
            return False
        return record.confidence_score >= AUTO_EXECUTE_THRESHOLD

    def _graduate(self, record) -> None:
        """Graduate an action type to auto-execute."""
        record.is_graduated = True
        record.graduated_at = datetime.now(timezone.utc)
        record.revoked_at = None

    def _should_revoke(self, record) -> bool:
        """
        Check if post-graduation failures warrant revoking auto-execute.
        Looks at recent auto-executed actions for failure rate.
        """
        recent_actions = (
            self.db.query(self.AgentAction)
            .filter(
                self.AgentAction.organization_id == record.organization_id,
                self.AgentAction.action_type == record.action_type,
                self.AgentAction.requires_approval.is_(False),
            )
            .order_by(self.AgentAction.created_at.desc())
            .limit(REVOCATION_WINDOW)
            .all()
        )

        if len(recent_actions) < 10:
            return False

        failures = sum(1 for a in recent_actions if a.status == "failed")
        failure_rate = Decimal(str(failures)) / Decimal(str(len(recent_actions)))

        return failure_rate > REVOCATION_FAILURE_RATE

    def _revoke(self, record) -> None:
        """Revoke graduation — action type goes back to requiring approval.

        Resets counters so the action type must earn a fresh sample window
        before it can re-graduate. Without this, a 95% historical rate
        would cause instant re-graduation on the next approval.
        """
        record.is_graduated = False
        record.revoked_at = datetime.now(timezone.utc)
        record.total_proposed = 0
        record.total_approved = 0
        record.total_rejected = 0
        record.total_auto_executed = 0
        record.confidence_score = Decimal("0.0")
