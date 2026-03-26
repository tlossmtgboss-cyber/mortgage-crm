"""Voice Scheduling Workflow Service — manages async multi-step voice command workflows.

Handles the lifecycle: voice command -> contact lookup -> SMS -> conversation -> booking.
This is the persistent state machine for voice-to-scheduling workflows that span hours
(GAP-2 fix). Separate from voice_workflow_service.py which handles single-session
pre-approval letter workflows.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models.communication import Activity
from database.enums import ActivityType

logger = logging.getLogger(__name__)


# Valid state transitions for the voice scheduling workflow state machine.
# Terminal states (completed, expired, cancelled) have no outbound transitions.
# "failed" allows retry back to "initiated".
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "initiated": ["contact_found", "failed", "cancelled"],
    "contact_found": ["sms_sent", "failed", "cancelled"],
    "sms_sent": ["awaiting_reply", "failed", "cancelled"],
    "awaiting_reply": ["negotiating", "time_confirmed", "expired", "cancelled"],
    "negotiating": ["time_confirmed", "awaiting_reply", "expired", "cancelled"],
    "time_confirmed": ["appointment_booked", "failed", "cancelled"],
    "appointment_booked": ["completed", "failed"],
    "completed": [],
    "expired": [],
    "cancelled": [],
    "failed": ["initiated"],  # allow retry
}


def _mask_phone(phone: Optional[str]) -> str:
    """Mask phone number to last 4 digits for structured logging."""
    if not phone or len(phone) < 4:
        return "****"
    return f"****{phone[-4:]}"


class VoiceSchedulingWorkflowService:
    """Manages persistent voice command workflows that span multiple async events."""

    DEFAULT_EXPIRY_HOURS = 48
    MAX_TURNS = 8

    def __init__(self, db: Session, assistant_name: str = "Aria"):
        self.db = db
        self.assistant_name = assistant_name

    def create_workflow(
        self,
        organization_id: int,
        user_id: int,
        workflow_type: str,
        contact_name: str,
        contact_phone: str,
        contact_email: Optional[str] = None,
        lead_id: Optional[int] = None,
        meeting_type: str = "discovery_call",
        meeting_duration_minutes: int = 30,
        message_context: Optional[str] = None,
    ) -> "VoiceWorkflow":
        """Create a new voice workflow instance."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        # Check for existing active workflow with same contact within this org
        existing = (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.organization_id == organization_id,
                VoiceWorkflow.contact_phone == contact_phone,
                VoiceWorkflow.state.notin_([
                    VoiceWorkflowState.COMPLETED.value,
                    VoiceWorkflowState.EXPIRED.value,
                    VoiceWorkflowState.CANCELLED.value,
                    VoiceWorkflowState.FAILED.value,
                ])
            )
            .first()
        )
        if existing:
            logger.info(
                "Active workflow already exists for contact",
                extra={
                    "workflow_id": str(existing.id),
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                    "contact_phone": _mask_phone(contact_phone),
                    "existing_state": existing.state,
                },
            )
            return existing

        workflow = VoiceWorkflow(
            organization_id=organization_id,
            user_id=user_id,
            workflow_type=workflow_type,
            state=VoiceWorkflowState.INITIATED.value,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            lead_id=lead_id,
            meeting_type=meeting_type,
            meeting_duration_minutes=meeting_duration_minutes,
            message_context=message_context,
            conversation_history=[],
            turn_count=0,
            max_turns=self.MAX_TURNS,
            expires_at=datetime.utcnow() + timedelta(hours=self.DEFAULT_EXPIRY_HOURS),
        )
        self.db.add(workflow)
        self.db.flush()
        logger.info(
            "Workflow created",
            extra={
                "workflow_id": str(workflow.id),
                "organization_id": str(workflow.organization_id),
                "user_id": str(workflow.user_id),
                "contact_phone": _mask_phone(contact_phone),
                "workflow_type": workflow_type,
                "meeting_type": meeting_type,
            },
        )
        return workflow

    def find_active_workflow_by_phone(self, phone: str, organization_id: int) -> Optional["VoiceWorkflow"]:
        """Find an active workflow matching an inbound SMS sender phone.

        Args:
            phone: Normalized phone number of the inbound SMS sender.
            organization_id: Required tenant filter to prevent cross-tenant data access.
        """
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        result = (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.organization_id == organization_id,
                VoiceWorkflow.contact_phone == phone,
                VoiceWorkflow.state.in_([
                    VoiceWorkflowState.SMS_SENT.value,
                    VoiceWorkflowState.AWAITING_REPLY.value,
                    VoiceWorkflowState.NEGOTIATING.value,
                ]),
                VoiceWorkflow.expires_at > datetime.utcnow(),
            )
            .order_by(VoiceWorkflow.created_at.desc())
            .with_for_update(skip_locked=True)
            .first()
        )
        logger.info(
            "Workflow lookup by phone completed",
            extra={
                "organization_id": str(organization_id),
                "contact_phone": _mask_phone(phone),
                "found": result is not None,
                "workflow_id": str(result.id) if result else None,
            },
        )
        return result

    def find_active_workflow_by_phone_any_org(self, phone: str) -> Optional["VoiceWorkflow"]:
        """Fallback: find an active workflow matching a phone WITHOUT tenant filter.

        WARNING: This method searches across ALL organizations. It should ONLY be
        used when the caller cannot resolve an organization_id from the inbound
        "to" number (e.g., user_twilio_config table is missing/empty). Prefer
        find_active_workflow_by_phone() with an explicit organization_id whenever
        possible.

        The result MUST be used with the workflow's own organization_id for all
        downstream operations to maintain tenant isolation.

        Args:
            phone: Normalized phone number of the inbound SMS sender.
        """
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        logger.warning(
            "Cross-org workflow lookup invoked — org resolution failed for inbound number",
            extra={"contact_phone": _mask_phone(phone)},
        )

        result = (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.contact_phone == phone,
                VoiceWorkflow.state.in_([
                    VoiceWorkflowState.SMS_SENT.value,
                    VoiceWorkflowState.AWAITING_REPLY.value,
                    VoiceWorkflowState.NEGOTIATING.value,
                ]),
                VoiceWorkflow.expires_at > datetime.utcnow(),
            )
            .order_by(VoiceWorkflow.created_at.desc())
            .with_for_update(skip_locked=True)
            .first()
        )
        logger.info(
            "Cross-org workflow lookup completed",
            extra={
                "contact_phone": _mask_phone(phone),
                "found": result is not None,
                "workflow_id": str(result.id) if result else None,
                "resolved_org_id": str(result.organization_id) if result else None,
            },
        )
        return result

    def get_workflow(self, workflow_id: int, organization_id: int) -> Optional["VoiceWorkflow"]:
        """Get a workflow by ID with tenant isolation."""
        from database.models.voice_workflow import VoiceWorkflow
        return (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.id == workflow_id,
                VoiceWorkflow.organization_id == organization_id,
            )
            .first()
        )

    def get_active_workflows_for_user(self, user_id: int, organization_id: int) -> List["VoiceWorkflow"]:
        """Get all active workflows for a user."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        return (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.user_id == user_id,
                VoiceWorkflow.organization_id == organization_id,
                VoiceWorkflow.state.notin_([
                    VoiceWorkflowState.COMPLETED.value,
                    VoiceWorkflowState.EXPIRED.value,
                    VoiceWorkflowState.CANCELLED.value,
                    VoiceWorkflowState.FAILED.value,
                ]),
            )
            .order_by(VoiceWorkflow.created_at.desc())
            .all()
        )

    def advance_state(self, workflow: "VoiceWorkflow", new_state: str, **kwargs):
        """Transition workflow to a new state with optional metadata updates.

        Uses a savepoint to ensure the state change and audit record are atomic.
        If either fails, both are rolled back.

        Raises:
            ValueError: If the transition from the current state to new_state is not allowed.
        """
        old_state = workflow.state

        # Validate state transition
        allowed = VALID_TRANSITIONS.get(old_state, [])
        if new_state not in allowed:
            logger.warning(
                "Invalid state transition attempted",
                extra={
                    "workflow_id": str(workflow.id),
                    "organization_id": str(workflow.organization_id),
                    "user_id": str(workflow.user_id),
                    "old_state": old_state,
                    "new_state": new_state,
                    "allowed_transitions": allowed,
                },
            )
            raise ValueError(
                f"Invalid state transition: '{old_state}' -> '{new_state}'. "
                f"Allowed transitions from '{old_state}': {allowed}"
            )

        # Atomic: state change + audit record in a savepoint
        savepoint = self.db.begin_nested()
        try:
            workflow.transition_to(new_state)

            for key, value in kwargs.items():
                if hasattr(workflow, key):
                    setattr(workflow, key, value)

            # Audit log
            activity = Activity(
                organization_id=workflow.organization_id,
                user_id=workflow.user_id,
                type=ActivityType.NOTE,
                content=f"Voice scheduling workflow {workflow.id} transitioned: {old_state} -> {new_state}",
                lead_id=workflow.lead_id,
                created_at=datetime.utcnow(),
            )
            self.db.add(activity)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise

        self.db.flush()
        logger.info(
            "Workflow state advanced",
            extra={
                "workflow_id": str(workflow.id),
                "organization_id": str(workflow.organization_id),
                "user_id": str(workflow.user_id),
                "contact_phone": _mask_phone(workflow.contact_phone),
                "old_state": old_state,
                "new_state": new_state,
            },
        )

    def expire_stale_workflows(self) -> int:
        """Expire workflows past their expiration time. Returns count expired."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        stale = (
            self.db.query(VoiceWorkflow)
            .filter(
                VoiceWorkflow.expires_at <= datetime.utcnow(),
                VoiceWorkflow.state.notin_([
                    VoiceWorkflowState.COMPLETED.value,
                    VoiceWorkflowState.EXPIRED.value,
                    VoiceWorkflowState.CANCELLED.value,
                    VoiceWorkflowState.FAILED.value,
                ]),
            )
            .all()
        )

        for wf in stale:
            old_state = wf.state

            # Atomic: state change + audit record in a savepoint
            savepoint = self.db.begin_nested()
            try:
                wf.transition_to(VoiceWorkflowState.EXPIRED.value)

                # Audit log for expiration
                activity = Activity(
                    organization_id=wf.organization_id,
                    user_id=wf.user_id,
                    type=ActivityType.NOTE,
                    content=f"Voice scheduling workflow {wf.id} expired (was in state: {old_state})",
                    lead_id=wf.lead_id,
                    created_at=datetime.utcnow(),
                )
                self.db.add(activity)
                savepoint.commit()
            except Exception:
                savepoint.rollback()
                logger.exception(
                    "Failed to expire workflow atomically",
                    extra={
                        "workflow_id": str(wf.id),
                        "organization_id": str(wf.organization_id),
                        "old_state": old_state,
                    },
                )
                continue

            logger.info(
                "Stale workflow expired",
                extra={
                    "workflow_id": str(wf.id),
                    "organization_id": str(wf.organization_id),
                    "user_id": str(wf.user_id),
                    "contact_phone": _mask_phone(wf.contact_phone),
                    "old_state": old_state,
                },
            )

        self.db.flush()
        logger.info(
            "Stale workflow expiration sweep completed",
            extra={"expired_count": len(stale)},
        )
        return len(stale)

    def cancel_workflow(self, workflow_id: int, organization_id: int) -> bool:
        """Cancel a workflow with tenant isolation.

        Args:
            workflow_id: ID of the workflow to cancel.
            organization_id: Required tenant filter to prevent cross-tenant cancellation.
        """
        from database.models.voice_workflow import VoiceWorkflowState

        workflow = self.get_workflow(workflow_id, organization_id)
        if not workflow or not workflow.is_active():
            logger.info(
                "Cancel workflow failed: not found or not active",
                extra={
                    "workflow_id": str(workflow_id),
                    "organization_id": str(organization_id),
                    "found": workflow is not None,
                    "is_active": workflow.is_active() if workflow else False,
                },
            )
            return False

        old_state = workflow.state

        # Atomic: state change + audit record in a savepoint
        savepoint = self.db.begin_nested()
        try:
            workflow.transition_to(VoiceWorkflowState.CANCELLED.value)

            # Audit log for cancellation
            activity = Activity(
                organization_id=workflow.organization_id,
                user_id=workflow.user_id,
                type=ActivityType.NOTE,
                content=f"Voice scheduling workflow {workflow.id} cancelled (was in state: {old_state})",
                lead_id=workflow.lead_id,
                created_at=datetime.utcnow(),
            )
            self.db.add(activity)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise

        self.db.flush()
        logger.info(
            "Workflow cancelled",
            extra={
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "user_id": str(workflow.user_id),
                "contact_phone": _mask_phone(workflow.contact_phone),
                "old_state": old_state,
            },
        )
        return True

    def to_status_dict(self, workflow: "VoiceWorkflow") -> Dict[str, Any]:
        """Convert workflow to a status dict for frontend display."""
        return {
            "workflow_id": workflow.id,
            "type": workflow.workflow_type,
            "state": workflow.state,
            "contact_name": workflow.contact_name,
            "contact_phone": _mask_phone(workflow.contact_phone),
            "meeting_type": workflow.meeting_type,
            "turn_count": workflow.turn_count,
            "max_turns": workflow.max_turns,
            "confirmed_datetime": workflow.confirmed_datetime.isoformat() if workflow.confirmed_datetime else None,
            "appointment_id": workflow.appointment_id,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
            "expires_at": workflow.expires_at.isoformat() if workflow.expires_at else None,
            "error": workflow.error_message,
        }
