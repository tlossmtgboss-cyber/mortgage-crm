"""
Appointment State Machine - Validates and enforces status transitions.

Centralizes all appointment status transition logic so that invalid transitions
(e.g., completing a cancelled appointment) are caught at the domain layer rather
than relying on each route handler to check manually.

Usage:
    from services.appointment_state_machine import AppointmentStateMachine

    # Check if a transition is allowed
    if AppointmentStateMachine.can_transition("booked", "confirmed"):
        ...

    # Perform a validated transition (updates model + creates history record)
    AppointmentStateMachine.transition(
        db=db,
        appointment=appointment,
        to_status="confirmed",
        changed_by=user_id,
        reason="Customer confirmed via email",
        change_source="system",
    )
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from exceptions import InvalidStateTransitionError

logger = logging.getLogger(__name__)


class AppointmentStateMachine:
    """
    Defines and enforces valid appointment status transitions.

    The transition graph:

        tentative  --> booked, cancelled
        booked     --> confirmed, cancelled, rescheduled
        confirmed  --> in_progress, no_show, cancelled, rescheduled
        in_progress --> completed, no_show
        completed  --> (terminal)
        no_show    --> rescheduled
        cancelled  --> (terminal)
        rescheduled --> booked, confirmed
    """

    # Valid transitions: from_status -> list of allowed to_statuses
    TRANSITIONS = {
        "tentative": ["booked", "cancelled"],
        "booked": ["confirmed", "cancelled", "rescheduled"],
        "confirmed": ["in_progress", "no_show", "cancelled", "rescheduled"],
        "in_progress": ["completed", "no_show"],
        "completed": [],       # terminal state
        "no_show": ["rescheduled"],  # can reschedule after no-show
        "cancelled": [],       # terminal state
        "rescheduled": ["booked", "confirmed"],  # goes back into the booking flow
    }

    # Terminal states that cannot transition to anything
    TERMINAL_STATES = frozenset(
        status for status, targets in TRANSITIONS.items() if not targets
    )

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """
        Check whether a transition from from_status to to_status is allowed.

        Args:
            from_status: Current status value (e.g., "booked").
            to_status: Desired target status (e.g., "confirmed").

        Returns:
            True if the transition is valid, False otherwise.
        """
        from_status = cls._normalize(from_status)
        to_status = cls._normalize(to_status)
        allowed = cls.TRANSITIONS.get(from_status, [])
        return to_status in allowed

    @classmethod
    def get_allowed_transitions(cls, current_status: str) -> List[str]:
        """
        Return the list of statuses that current_status can transition to.

        Args:
            current_status: The current status value.

        Returns:
            List of valid target status strings. Empty list for terminal states
            or unknown statuses.
        """
        current_status = cls._normalize(current_status)
        return list(cls.TRANSITIONS.get(current_status, []))

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """Check whether a status is terminal (no further transitions allowed)."""
        return cls._normalize(status) in cls.TERMINAL_STATES

    @classmethod
    def transition(
        cls,
        db,
        appointment,
        to_status: str,
        changed_by: Optional[int] = None,
        reason: Optional[str] = None,
        change_source: str = "manual",
    ) -> None:
        """
        Validate and execute a status transition on an appointment.

        This method:
        1. Validates the transition is allowed
        2. Updates the appointment's status and status_changed_at
        3. Sets status-specific timestamps (completed_at, no_show_at, cancelled_at)
        4. Creates an AppointmentStatusHistory record

        Args:
            db: SQLAlchemy session.
            appointment: The Appointment ORM instance to transition.
            to_status: Target status string (e.g., "confirmed").
            changed_by: User ID performing the change (nullable for system changes).
            reason: Optional reason for the transition.
            change_source: One of "manual", "ai", "system", "webhook".

        Raises:
            InvalidStateTransitionError: If the transition is not allowed.
        """
        # Import AppointmentStatus enum lazily to avoid circular imports
        from smart_scheduler_models import AppointmentStatus

        # Normalize the current status from the appointment
        current_status_raw = appointment.status
        if hasattr(current_status_raw, 'value'):
            from_status = current_status_raw.value
        else:
            from_status = str(current_status_raw)

        to_status_normalized = cls._normalize(to_status)

        # Validate the transition
        if not cls.can_transition(from_status, to_status_normalized):
            allowed = cls.get_allowed_transitions(from_status)
            raise InvalidStateTransitionError(
                from_status=from_status,
                to_status=to_status_normalized,
                entity_type="Appointment",
                allowed_transitions=allowed,
            )

        now = datetime.now(timezone.utc)

        # Resolve the enum value for the new status
        new_status_enum = AppointmentStatus(to_status_normalized)

        # Update the appointment
        appointment.status = new_status_enum
        appointment.status_changed_at = now
        appointment.status_changed_by = changed_by

        # Set status-specific timestamps
        if to_status_normalized == "completed":
            appointment.completed_at = now
        elif to_status_normalized == "no_show":
            appointment.no_show_at = now
        elif to_status_normalized == "cancelled":
            appointment.cancelled_at = now
            if reason:
                appointment.cancellation_reason = reason

        # Create history record
        # We need the AppointmentStatusHistory model from the same factory.
        # Since models are created via create_smart_scheduler_models(Base), we
        # look it up from the appointment's class registry.
        AppointmentStatusHistory = cls._get_history_model(appointment)

        if AppointmentStatusHistory is not None:
            history = AppointmentStatusHistory(
                appointment_id=appointment.id,
                from_status=from_status,
                to_status=to_status_normalized,
                changed_by=changed_by,
                changed_at=now,
                reason=reason,
                change_source=change_source,
            )
            db.add(history)

        logger.info(
            f"Appointment {appointment.id}: {from_status} -> {to_status_normalized} "
            f"(by user {changed_by}, source={change_source})"
        )

    @classmethod
    def _get_history_model(cls, appointment):
        """
        Resolve the AppointmentStatusHistory model class from the appointment's
        SQLAlchemy mapper registry. This handles the factory-created model pattern
        where models are created dynamically via create_smart_scheduler_models(Base).
        """
        try:
            # The relationship 'status_history' is defined on Appointment,
            # so we can get the target model from the relationship property.
            from sqlalchemy import inspect
            mapper = inspect(type(appointment))
            for rel in mapper.relationships:
                if rel.key == "status_history":
                    return rel.mapper.class_
        except Exception as e:
            logger.warning(f"Could not resolve AppointmentStatusHistory model: {e}")

        # Fallback: try importing from the mapper registry directly
        try:
            base_class = type(appointment).__bases__[0]  # The Base class
            for cls_ref in base_class.registry._class_registry.values():
                if hasattr(cls_ref, '__tablename__') and cls_ref.__tablename__ == 'appointment_status_history':
                    return cls_ref
        except Exception as e:
            logger.warning(f"Fallback history model lookup failed: {e}")

        return None

    @staticmethod
    def _normalize(status: str) -> str:
        """Normalize a status value to lowercase string."""
        if hasattr(status, 'value'):
            return status.value.lower()
        return str(status).lower()
