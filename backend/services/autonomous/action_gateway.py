"""Action Gateway — confidence-gated execution for autonomous agents.

Every autonomous action flows through this gateway to enable:
1. AgentAction audit trail (what the AI did)
2. Confidence-based approval gating (should a human review this first?)
3. Progressive autonomy (watch → suggest → auto-execute)

The gateway wraps the existing ConfidenceGraduationService and AgentAction
model into a single call that agents use instead of raw db.add().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ActionGateway:
    """Confidence-gated action execution for autonomous agents.

    Usage inside an agent::

        gateway = ActionGateway(db, org_id, execution_id)

        # Propose an action — gateway decides whether to execute or hold
        notification = Notification(...)
        executed = gateway.propose(
            "create_notification",
            lambda: db.add(notification),
            target_entity="loan",
            target_id=loan.id,
            description="Stalled loan alert for LO",
        )

        # At the end of run(), include gateway.stats in the summary
        return {"actions": gateway.stats, ...}
    """

    ALWAYS_EXECUTE = frozenset({
        "create_activity",
        "create_compliance_alert",
        "create_morning_briefing",
        "update_compliance_alert",
    })

    def __init__(
        self,
        db: Session,
        org_id: int,
        execution_id: Optional[int] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.execution_id = execution_id
        self._grad_service = None
        self._proposed = 0
        self._auto_executed = 0
        self._held = 0
        self._skipped_safety = 0

    @property
    def grad_service(self):
        if self._grad_service is None:
            from services.autonomous.confidence_graduation import (
                ConfidenceGraduationService,
            )
            self._grad_service = ConfidenceGraduationService(self.db)
        return self._grad_service

    def propose(
        self,
        action_type: str,
        execute_fn: Callable[[], Any],
        *,
        target_entity: Optional[str] = None,
        target_id: Optional[int] = None,
        description: str = "",
        payload: Optional[dict] = None,
        notify_user_id: Optional[int] = None,
    ) -> bool:
        """Propose an action through the confidence gate.

        Returns True if the action was executed, False if held for approval.

        Safety-critical action types in ALWAYS_EXECUTE bypass the gate
        and execute immediately (compliance alerts must never be delayed).

        If ``notify_user_id`` is provided and the action is auto-executed
        (graduated), an in-app Notification is created so the user knows
        AI handled it.
        """
        if isinstance(target_id, str):
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                target_id = None

        if action_type in self.ALWAYS_EXECUTE:
            try:
                execute_fn()
                self._skipped_safety += 1
                self._record_action(action_type, "completed", False,
                                    target_entity, target_id, description, payload)
                return True
            except Exception as e:
                logger.warning("Safety action %s failed: %s", action_type, e)
                return False

        needs_approval = True
        try:
            needs_approval = self.grad_service.requires_approval(
                self.org_id, action_type
            )
        except Exception:
            pass

        self._proposed += 1

        if not needs_approval:
            try:
                execute_fn()
                self._auto_executed += 1
                self._record_action(action_type, "completed", False,
                                    target_entity, target_id, description, payload)
                self._notify_auto_action(
                    notify_user_id, action_type, description,
                    target_entity, target_id,
                )
                return True
            except Exception as e:
                logger.warning("Auto-executed action %s failed: %s", action_type, e)
                self._record_action(action_type, "failed", False,
                                    target_entity, target_id, description,
                                    {**(payload or {}), "error": str(e)})
                return False
        else:
            self._held += 1
            self._record_action(action_type, "pending_approval", True,
                                target_entity, target_id, description, payload)
            return False

    def _record_action(
        self,
        action_type: str,
        status: str,
        requires_approval: bool,
        target_entity: Optional[str],
        target_id: Optional[int],
        description: str,
        payload: Optional[dict],
    ):
        """Persist an AgentAction record for audit and confidence tracking."""
        if isinstance(target_id, str):
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                target_id = None
        try:
            from database.models.autonomous_task import AgentAction

            action = AgentAction(
                execution_id=self.execution_id,
                organization_id=self.org_id,
                action_type=action_type,
                target_entity=target_entity,
                target_id=target_id,
                description=description,
                payload=payload,
                status=status,
                requires_approval=requires_approval,
            )
            self.db.add(action)
            self.db.flush()
        except Exception as e:
            logger.warning("Failed to record AgentAction: %s", e)

    def _notify_auto_action(
        self,
        user_id: Optional[int],
        action_type: str,
        description: str,
        target_entity: Optional[str],
        target_id: Optional[int],
    ):
        """Create an in-app Notification so the user knows AI auto-handled something."""
        if not user_id:
            return
        # The action itself IS a notification — skip the meta-notification to avoid doubles
        if action_type == "create_notification":
            return
        try:
            from database.models.security import Notification

            link = self._build_link(target_entity, target_id)
            notification = Notification(
                user_id=user_id,
                organization_id=self.org_id,
                type="ai_auto_action",
                title=f"AI Handled: {description[:80]}",
                message=(
                    f"{description}. "
                    "This was auto-processed based on your approval history."
                ),
                link=link,
                is_read=False,
            )
            self.db.add(notification)
            self.db.flush()
        except Exception as e:
            logger.warning("Failed to create auto-action notification: %s", e)

    @staticmethod
    def _build_link(target_entity: Optional[str], target_id: Optional[int]) -> Optional[str]:
        """Build a frontend link from entity type and ID."""
        if not target_entity or not target_id:
            return None
        entity_paths = {
            "loan": f"/pipeline/loans/{target_id}",
            "lead": f"/clients/{target_id}",
            "task": f"/tasks/{target_id}",
            "contact": f"/clients/{target_id}",
        }
        return entity_paths.get(target_entity)

    @property
    def stats(self) -> dict:
        return {
            "proposed": self._proposed,
            "auto_executed": self._auto_executed,
            "held_for_approval": self._held,
            "safety_bypassed": self._skipped_safety,
        }
