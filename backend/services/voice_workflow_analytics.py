"""Voice Workflow Analytics — event tracking for workflow lifecycle metrics.

Emits structured analytics events for workflow state transitions, completion rates,
conversation turn counts, and timing metrics. Events are logged in a structured
format that can be consumed by any analytics backend (DataDog, Mixpanel, etc.).
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VoiceWorkflowAnalytics:
    """Emits analytics events for voice workflow lifecycle."""

    @staticmethod
    def track_workflow_created(
        workflow_id: int,
        organization_id: int,
        user_id: int,
        workflow_type: str,
        meeting_type: str,
    ):
        """Track workflow creation event."""
        logger.info(
            "analytics.voice_workflow.created",
            extra={
                "event": "voice_workflow.created",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "workflow_type": workflow_type,
                "meeting_type": meeting_type,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_state_transition(
        workflow_id: int,
        organization_id: int,
        old_state: str,
        new_state: str,
        turn_count: int = 0,
    ):
        """Track workflow state transition."""
        logger.info(
            "analytics.voice_workflow.state_transition",
            extra={
                "event": "voice_workflow.state_transition",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "old_state": old_state,
                "new_state": new_state,
                "turn_count": turn_count,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_workflow_completed(
        workflow_id: int,
        organization_id: int,
        user_id: int,
        turn_count: int,
        duration_seconds: Optional[float] = None,
        appointment_id: Optional[int] = None,
    ):
        """Track successful workflow completion with metrics."""
        logger.info(
            "analytics.voice_workflow.completed",
            extra={
                "event": "voice_workflow.completed",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "turn_count": turn_count,
                "duration_seconds": duration_seconds,
                "appointment_id": str(appointment_id) if appointment_id else None,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_workflow_failed(
        workflow_id: int,
        organization_id: int,
        failure_state: str,
        error_message: Optional[str] = None,
        turn_count: int = 0,
    ):
        """Track workflow failure."""
        logger.info(
            "analytics.voice_workflow.failed",
            extra={
                "event": "voice_workflow.failed",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "failure_state": failure_state,
                "error_message": error_message,
                "turn_count": turn_count,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_workflow_expired(
        workflow_id: int,
        organization_id: int,
        last_state: str,
        turn_count: int = 0,
    ):
        """Track workflow expiration."""
        logger.info(
            "analytics.voice_workflow.expired",
            extra={
                "event": "voice_workflow.expired",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "last_state": last_state,
                "turn_count": turn_count,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_sms_sent(
        workflow_id: int,
        organization_id: int,
        message_type: str,  # "initial", "follow_up", "confirmation"
    ):
        """Track outbound SMS event."""
        logger.info(
            "analytics.voice_workflow.sms_sent",
            extra={
                "event": "voice_workflow.sms_sent",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "message_type": message_type,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_sms_received(
        workflow_id: int,
        organization_id: int,
        intent: str,  # "confirm_time", "suggest_alternative", "decline", etc.
    ):
        """Track inbound SMS reply with classified intent."""
        logger.info(
            "analytics.voice_workflow.sms_received",
            extra={
                "event": "voice_workflow.sms_received",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "classified_intent": intent,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    def track_appointment_booked(
        workflow_id: int,
        organization_id: int,
        appointment_id: int,
        negotiation_turns: int,
    ):
        """Track successful appointment booking from workflow."""
        logger.info(
            "analytics.voice_workflow.appointment_booked",
            extra={
                "event": "voice_workflow.appointment_booked",
                "workflow_id": str(workflow_id),
                "organization_id": str(organization_id),
                "appointment_id": str(appointment_id),
                "negotiation_turns": negotiation_turns,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
