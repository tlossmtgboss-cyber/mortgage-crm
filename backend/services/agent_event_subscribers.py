"""
Agent-specific event subscribers for the EventBus.

Subscribes to both appointment lifecycle events (existing) and the new
inter-agent events so that agents can react to system-wide activity.

Call ``register_agent_subscribers()`` during application startup, after
the base ``register_all_subscribers()`` from ``event_subscribers.py``.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


# =============================================================================
# Appointment lifecycle -> agent notifications
# =============================================================================

async def on_appointment_created_notify_scheduler_agent(event: Event) -> None:
    """When an appointment is created, notify agents that track scheduling."""
    data = event.data
    appointment_id = data.get("appointment_id")
    lead_id = data.get("lead_id")

    if not appointment_id:
        return

    logger.info(
        "[AGENT-EVENTS] Appointment %s created -- notifying agents [%s]",
        appointment_id, event.correlation_id,
    )

    try:
        from services.agent_event_bridge import agent_event_bridge, AGENT_LEAD

        # If this appointment is tied to a lead, let the lead nurturer know
        if lead_id:
            await agent_event_bridge._send_message(
                to_agent_id=AGENT_LEAD,
                subject=f"Appointment scheduled for lead {lead_id}",
                content=(
                    f"Appointment {appointment_id} has been created for lead {lead_id}. "
                    "Update lead engagement score and adjust follow-up cadence."
                ),
                payload={
                    "appointment_id": appointment_id,
                    "lead_id": lead_id,
                    "attendee_email": data.get("attendee_email"),
                },
                priority="normal",
            )
    except Exception as e:
        logger.warning("[AGENT-EVENTS] Failed to notify agents on appointment: %s", e)
        raise  # Let EventBus isolate


async def on_appointment_no_show_notify_agents(event: Event) -> None:
    """When a no-show occurs, notify lead nurturer and ops."""
    data = event.data
    appointment_id = data.get("appointment_id")
    lead_id = data.get("lead_id")
    lo_id = data.get("assigned_user_id")

    if not appointment_id:
        return

    logger.info(
        "[AGENT-EVENTS] Appointment %s no-show -- notifying agents [%s]",
        appointment_id, event.correlation_id,
    )

    try:
        from services.agent_event_bridge import agent_event_bridge, AGENT_LEAD, AGENT_OPS

        if lead_id:
            await agent_event_bridge._send_message(
                to_agent_id=AGENT_LEAD,
                subject=f"No-show: appointment {appointment_id}, lead {lead_id}",
                content=(
                    f"Lead {lead_id} was a no-show for appointment {appointment_id}. "
                    "Consider re-engagement outreach."
                ),
                payload={"appointment_id": appointment_id, "lead_id": lead_id},
                priority="high",
            )

        await agent_event_bridge._send_message(
            to_agent_id=AGENT_OPS,
            subject=f"No-show: appointment {appointment_id}",
            content=f"Appointment {appointment_id} resulted in a no-show.",
            payload={"appointment_id": appointment_id, "lo_id": lo_id},
            priority="normal",
        )
    except Exception as e:
        logger.warning("[AGENT-EVENTS] Failed to notify agents on no-show: %s", e)
        raise


# =============================================================================
# Inter-agent event subscribers (react to bridge-emitted events)
# =============================================================================

async def on_loan_stage_changed_trigger_compliance(event: Event) -> None:
    """When a loan changes stage, trigger a compliance timeline check."""
    data = event.data
    loan_id = data.get("loan_id")
    new_stage = data.get("new_stage")

    if not loan_id:
        return

    logger.info(
        "[AGENT-EVENTS] Loan %s -> %s: checking compliance triggers [%s]",
        loan_id, new_stage, event.correlation_id,
    )
    # The actual compliance check is handled by the message that
    # AgentEventBridge.on_loan_stage_changed already sends to compliance_checker.
    # This subscriber exists for additional side effects (e.g., audit logging).


async def on_compliance_violation_audit_log(event: Event) -> None:
    """Log compliance violations to the audit trail."""
    data = event.data
    loan_id = data.get("loan_id")
    violation_type = data.get("violation_type")
    severity = data.get("severity")

    logger.warning(
        "[AGENT-EVENTS] COMPLIANCE VIOLATION audit: loan=%s type=%s severity=%s [%s]",
        loan_id, violation_type, severity, event.correlation_id,
    )


async def on_hot_lead_push_notification(event: Event) -> None:
    """Send a push notification to the assigned LO when a hot lead is detected."""
    data = event.data
    lead_id = data.get("lead_id")
    score = data.get("score")
    lo_id = data.get("lo_id")

    if not lo_id:
        return

    logger.info(
        "[AGENT-EVENTS] Hot lead %s (score=%s) -- push to LO %s [%s]",
        lead_id, score, lo_id, event.correlation_id,
    )

    try:
        from services.push_notification_service import send_push_to_user
        await _call_or_run(
            send_push_to_user,
            user_id=lo_id,
            title="Hot Lead Alert",
            body=f"Lead #{lead_id} scored {score} -- follow up now!",
            data={"type": "hot_lead", "lead_id": str(lead_id)},
        )
    except (ImportError, AttributeError):
        logger.debug("[AGENT-EVENTS] Push notification service not available")
    except Exception as e:
        logger.warning("[AGENT-EVENTS] Push notification failed for LO %s: %s", lo_id, e)
        raise


# =============================================================================
# Registration
# =============================================================================

def register_agent_subscribers() -> None:
    """Register all agent-related event subscribers.  Call once at startup."""

    # Appointment lifecycle -> agent notifications
    event_bus.subscribe(
        EventType.APPOINTMENT_CREATED,
        on_appointment_created_notify_scheduler_agent,
    )
    event_bus.subscribe(
        EventType.APPOINTMENT_NO_SHOW,
        on_appointment_no_show_notify_agents,
    )

    # Inter-agent events
    event_bus.subscribe(
        EventType.LOAN_STAGE_CHANGED,
        on_loan_stage_changed_trigger_compliance,
    )
    event_bus.subscribe(
        EventType.COMPLIANCE_VIOLATION,
        on_compliance_violation_audit_log,
    )
    event_bus.subscribe(
        EventType.HOT_LEAD_DETECTED,
        on_hot_lead_push_notification,
    )

    logger.info(
        "[AGENT-EVENTS] Registered %d agent event subscribers",
        5,  # Count of subscriptions above
    )


# =============================================================================
# Helpers
# =============================================================================

async def _call_or_run(fn, **kwargs):
    """Call *fn* with **kwargs, awaiting if it returns a coroutine."""
    import asyncio
    import inspect

    if asyncio.iscoroutinefunction(fn):
        return await fn(**kwargs)
    elif inspect.isgeneratorfunction(fn):
        return fn(**kwargs)
    else:
        loop = asyncio.get_running_loop()
        import functools
        return await loop.run_in_executor(None, functools.partial(fn, **kwargs))
