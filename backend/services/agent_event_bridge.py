"""
Agent Event Bridge

Connects agent tool outputs to other agents via the EventBus and MessageBus.
When one agent detects something noteworthy (stalled loan, hot lead, expired
documents, compliance violation), this bridge publishes events so that other
agents can react asynchronously.

All operations are fire-and-forget: failures are logged, never propagated.

Usage (from any agent tool or node):
    from services.agent_event_bridge import agent_event_bridge
    await agent_event_bridge.on_loan_stalled(loan_id=42, days_stale=14, ...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


# =============================================================================
# Well-known agent IDs (match tool_integration.py AGENT_CONFIGS keys)
# =============================================================================

AGENT_PIPELINE = "pipeline_analyst"
AGENT_COMPLIANCE = "compliance_checker"
AGENT_LEAD = "lead_nurturer"
AGENT_DOCUMENT = "document_tracker"
AGENT_CUSTOMER = "customer_intelligence"
AGENT_OPS = "ops_manager"
AGENT_BRIDGE = "agent_event_bridge"  # Synthetic source ID for bridge-originated msgs


# =============================================================================
# MessageBus helper (lazy import to avoid circular deps)
# =============================================================================

def _get_message_bus():
    """Lazily obtain a MessageBus instance backed by a fresh DB session.

    Returns None (with a warning) if the infrastructure is unavailable,
    so that callers degrade gracefully.
    """
    try:
        from ai_services import MessageBus
        from database import SessionLocal
        session = SessionLocal()
        return MessageBus(session), session
    except Exception as e:
        logger.debug("MessageBus unavailable (non-fatal): %s", e)
        return None, None


async def _send_bus_message(
    to_agent_id: str,
    subject: str,
    content: str,
    payload: Dict[str, Any],
    priority: str = "normal",
    message_type: str = "broadcast",
):
    """Send a message via the DB-backed MessageBus (fire-and-forget).

    Runs the synchronous DB write in a thread executor so it never blocks
    the async caller.
    """
    try:
        from ai_models import AgentMessage, MessageType, Priority

        priority_map = {
            "low": Priority.LOW,
            "normal": Priority.NORMAL,
            "high": Priority.HIGH,
            "urgent": Priority.URGENT,
        }
        type_map = {
            "request": MessageType.REQUEST,
            "response": MessageType.RESPONSE,
            "broadcast": MessageType.BROADCAST,
            "escalation": MessageType.ESCALATION,
        }

        message = AgentMessage(
            message_id=uuid.uuid4().hex[:16],
            from_agent_id=AGENT_BRIDGE,
            to_agent_id=to_agent_id,
            message_type=type_map.get(message_type, MessageType.BROADCAST),
            subject=subject,
            content=content,
            payload=payload,
            priority=priority_map.get(priority, Priority.NORMAL),
            requires_human_review=False,
        )

        bus, session = _get_message_bus()
        if bus is None:
            return

        try:
            # MessageBus.send_message is async but uses synchronous DB calls;
            # run it in the default executor to avoid blocking.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sync_send, bus, message)
        finally:
            if session is not None:
                session.close()

    except Exception as e:
        logger.warning("Failed to send MessageBus message to %s: %s", to_agent_id, e)


def _sync_send(bus, message):
    """Synchronous wrapper around the async send_message."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bus.send_message(message))
    finally:
        loop.close()


# =============================================================================
# AgentEventBridge
# =============================================================================

class AgentEventBridge:
    """Connects agent outputs to other agent inputs via events.

    Every ``on_*`` method:
    1. Publishes an event to the in-process EventBus (subscribers run inline).
    2. Persists a message in the DB-backed MessageBus for async processing.

    Both steps are guarded: if either fails the other still runs, and
    exceptions never propagate to the caller.

    Deduplication: recently emitted events are tracked in an in-memory cache.
    If the same event (same type + entity + org) is emitted within the TTL
    window (default 5 minutes), the duplicate is silently skipped.
    """

    # In-memory dedup cache: key -> timestamp of last emission
    _dedup_cache: Dict[str, float] = {}
    _dedup_check_count: int = 0

    # ------------------------------------------------------------------
    # Deduplication helpers
    # ------------------------------------------------------------------

    def _is_duplicate_event(self, event_key: str, ttl_seconds: int = 300) -> bool:
        """Check if an event was recently emitted (within ttl_seconds).

        Also periodically cleans up stale entries to prevent unbounded growth.
        Returns True if the event is a duplicate and should be skipped.
        """
        now = time.monotonic()

        # Periodic cleanup: every 100 checks or when cache exceeds 1000 entries
        self.__class__._dedup_check_count += 1
        if self.__class__._dedup_check_count >= 100 or len(self.__class__._dedup_cache) > 1000:
            self._cleanup_dedup_cache(now, ttl_seconds)
            self.__class__._dedup_check_count = 0

        last_emitted = self.__class__._dedup_cache.get(event_key)
        if last_emitted is not None and (now - last_emitted) < ttl_seconds:
            logger.debug(
                "Dedup: skipping duplicate event %s (last emitted %.1fs ago)",
                event_key, now - last_emitted,
            )
            return True

        # Record this emission
        self.__class__._dedup_cache[event_key] = now
        return False

    @classmethod
    def _cleanup_dedup_cache(cls, now: float, ttl_seconds: int = 300) -> None:
        """Remove stale entries from the dedup cache."""
        stale_keys = [
            k for k, ts in cls._dedup_cache.items()
            if (now - ts) >= ttl_seconds
        ]
        for k in stale_keys:
            del cls._dedup_cache[k]
        if stale_keys:
            logger.debug("Dedup: cleaned up %d stale cache entries", len(stale_keys))

    # ------------------------------------------------------------------
    # Loan pipeline events
    # ------------------------------------------------------------------

    async def on_loan_stalled(
        self,
        loan_id: int,
        days_stale: int,
        stage: str,
        lo_id: Optional[int] = None,
        org_id: Optional[str] = None,
    ) -> None:
        """A loan has been sitting in the same stage beyond the SLA threshold."""
        dedup_key = f"loan_stalled:{loan_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "loan_id": loan_id,
            "days_stale": days_stale,
            "stage": stage,
            "lo_id": lo_id,
        }

        await self._publish_event(EventType.LOAN_STALLED, data, org_id=org_id)

        # Notify Document Tracker to check for missing docs
        await self._send_message(
            to_agent_id=AGENT_DOCUMENT,
            subject=f"Stalled loan {loan_id} -- check missing docs",
            content=(
                f"Loan {loan_id} has been in {stage} for {days_stale} days. "
                "Please verify all required documents are on file."
            ),
            payload=data,
            priority="high",
        )

        # Notify Lead Nurturer if borrower is also a lead
        await self._send_message(
            to_agent_id=AGENT_LEAD,
            subject=f"Stalled loan {loan_id} -- borrower follow-up",
            content=(
                f"Loan {loan_id} has stalled at {stage} ({days_stale} days). "
                "Check if the borrower has a matching lead record and send a status update."
            ),
            payload=data,
            priority="normal",
        )

        # Notify Customer Intelligence to send status update
        await self._send_message(
            to_agent_id=AGENT_CUSTOMER,
            subject=f"Stalled loan {loan_id} -- customer status update",
            content=(
                f"Loan {loan_id} has not progressed from {stage} in {days_stale} days. "
                "Consider proactive customer outreach."
            ),
            payload=data,
            priority="normal",
        )

        logger.info(
            "on_loan_stalled: loan_id=%s stage=%s days=%d",
            loan_id, stage, days_stale,
        )

    async def on_loan_stage_changed(
        self,
        loan_id: int,
        old_stage: str,
        new_stage: str,
        lo_id: Optional[int] = None,
        org_id: Optional[str] = None,
    ) -> None:
        """A loan has transitioned from one stage to another."""
        dedup_key = f"loan_stage_changed:{loan_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "loan_id": loan_id,
            "old_stage": old_stage,
            "new_stage": new_stage,
            "lo_id": lo_id,
        }

        await self._publish_event(EventType.LOAN_STAGE_CHANGED, data, org_id=org_id)

        # Notify Pipeline Analyst about stage movement
        await self._send_message(
            to_agent_id=AGENT_PIPELINE,
            subject=f"Loan {loan_id} moved {old_stage} -> {new_stage}",
            content=f"Loan {loan_id} transitioned from {old_stage} to {new_stage}.",
            payload=data,
            priority="normal",
        )

        # Notify Compliance on stage transitions that trigger disclosure checks
        disclosure_trigger_stages = {
            "DISCLOSED", "SUBMITTED", "APPROVED", "CLEAR_TO_CLOSE", "FUNDED",
        }
        if new_stage in disclosure_trigger_stages:
            await self._send_message(
                to_agent_id=AGENT_COMPLIANCE,
                subject=f"Loan {loan_id} reached {new_stage} -- compliance check",
                content=(
                    f"Loan {loan_id} entered {new_stage}. "
                    "Verify TRID timing and disclosure requirements."
                ),
                payload=data,
                priority="high",
            )

        logger.info(
            "on_loan_stage_changed: loan_id=%s %s -> %s",
            loan_id, old_stage, new_stage,
        )

    # ------------------------------------------------------------------
    # Lead events
    # ------------------------------------------------------------------

    async def on_hot_lead_detected(
        self,
        lead_id: int,
        score: int,
        lo_id: Optional[int] = None,
        org_id: Optional[str] = None,
    ) -> None:
        """A lead has been scored as hot (grade A/B, score >= 60)."""
        dedup_key = f"hot_lead_detected:{lead_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "lead_id": lead_id,
            "score": score,
            "lo_id": lo_id,
        }

        await self._publish_event(EventType.HOT_LEAD_DETECTED, data, org_id=org_id)

        # Notify Customer Intelligence to draft outreach
        await self._send_message(
            to_agent_id=AGENT_CUSTOMER,
            subject=f"Hot lead {lead_id} -- draft outreach",
            content=(
                f"Lead {lead_id} scored {score}. "
                "Trigger personalized outreach sequence."
            ),
            payload=data,
            priority="high",
        )

        logger.info(
            "on_hot_lead_detected: lead_id=%s score=%d lo=%s",
            lead_id, score, lo_id,
        )

    # ------------------------------------------------------------------
    # Document events
    # ------------------------------------------------------------------

    async def on_documents_expired(
        self,
        loan_id: int,
        doc_types: List[str],
        org_id: Optional[str] = None,
    ) -> None:
        """One or more documents on a loan have expired."""
        dedup_key = f"documents_expired:{loan_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "loan_id": loan_id,
            "doc_types": doc_types,
        }

        await self._publish_event(EventType.DOCUMENTS_EXPIRED, data, org_id=org_id)

        # Notify Compliance Checker
        await self._send_message(
            to_agent_id=AGENT_COMPLIANCE,
            subject=f"Expired docs on loan {loan_id}",
            content=(
                f"The following documents have expired on loan {loan_id}: "
                f"{', '.join(doc_types)}. Verify compliance impact."
            ),
            payload=data,
            priority="high",
        )

        # Notify Pipeline Analyst (may impact closing timeline)
        await self._send_message(
            to_agent_id=AGENT_PIPELINE,
            subject=f"Expired docs on loan {loan_id} -- timeline impact",
            content=(
                f"Loan {loan_id} has {len(doc_types)} expired document(s). "
                "Re-evaluate predicted closing timeline."
            ),
            payload=data,
            priority="normal",
        )

        logger.info(
            "on_documents_expired: loan_id=%s types=%s",
            loan_id, doc_types,
        )

    # ------------------------------------------------------------------
    # Compliance events
    # ------------------------------------------------------------------

    async def on_compliance_violation(
        self,
        loan_id: int,
        violation_type: str,
        severity: str,
        description: str = "",
        org_id: Optional[str] = None,
    ) -> None:
        """A compliance violation has been detected on a loan."""
        dedup_key = f"compliance_violation:{loan_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "loan_id": loan_id,
            "violation_type": violation_type,
            "severity": severity,
            "description": description,
        }

        await self._publish_event(EventType.COMPLIANCE_VIOLATION, data, org_id=org_id)

        if severity in ("critical", "high"):
            # Notify Ops Manager for critical/high violations
            await self._send_message(
                to_agent_id=AGENT_OPS,
                subject=f"Compliance violation on loan {loan_id} [{severity}]",
                content=(
                    f"Violation: {violation_type} ({severity}) on loan {loan_id}. "
                    f"{description}"
                ),
                payload=data,
                priority="urgent" if severity == "critical" else "high",
                message_type="escalation",
            )

        # Always notify the Pipeline Analyst so the pipeline view stays accurate
        await self._send_message(
            to_agent_id=AGENT_PIPELINE,
            subject=f"Compliance issue on loan {loan_id}",
            content=f"{violation_type}: {description}",
            payload=data,
            priority="normal",
        )

        logger.info(
            "on_compliance_violation: loan_id=%s type=%s severity=%s",
            loan_id, violation_type, severity,
        )

    # ------------------------------------------------------------------
    # Email / inbound data events
    # ------------------------------------------------------------------

    async def on_email_data_extracted(
        self,
        loan_id: int,
        extracted_fields: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> None:
        """Email processor has extracted structured data for a loan."""
        dedup_key = f"email_data_extracted:{loan_id}:{org_id}"
        if self._is_duplicate_event(dedup_key):
            return

        data = {
            "loan_id": loan_id,
            "extracted_fields": extracted_fields,
        }

        await self._publish_event(EventType.EMAIL_DATA_EXTRACTED, data, org_id=org_id)

        # If documents were attached / referenced, notify Document Tracker
        doc_fields = {
            k: v for k, v in extracted_fields.items()
            if "doc" in k.lower() or "document" in k.lower() or "attachment" in k.lower()
        }
        if doc_fields:
            await self._send_message(
                to_agent_id=AGENT_DOCUMENT,
                subject=f"Email data for loan {loan_id} -- document update",
                content=(
                    f"Email processor extracted document-related data for loan {loan_id}: "
                    f"{json.dumps(doc_fields, default=str)}"
                ),
                payload=data,
                priority="normal",
            )

        # If status/stage info was extracted, notify Pipeline
        status_fields = {
            k: v for k, v in extracted_fields.items()
            if "status" in k.lower() or "stage" in k.lower()
        }
        if status_fields:
            await self._send_message(
                to_agent_id=AGENT_PIPELINE,
                subject=f"Email data for loan {loan_id} -- status update",
                content=(
                    f"Email processor extracted status info for loan {loan_id}: "
                    f"{json.dumps(status_fields, default=str)}"
                ),
                payload=data,
                priority="normal",
            )

        logger.info(
            "on_email_data_extracted: loan_id=%s fields=%d",
            loan_id, len(extracted_fields),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> None:
        """Publish an event to the in-process EventBus. Never raises."""
        try:
            event = Event(
                type=event_type,
                data=data,
                source=AGENT_BRIDGE,
                org_id=org_id,
            )
            await event_bus.publish(event)
        except Exception as e:
            logger.warning(
                "EventBus publish failed for %s: %s", event_type.value, e
            )

    async def _send_message(
        self,
        to_agent_id: str,
        subject: str,
        content: str,
        payload: Dict[str, Any],
        priority: str = "normal",
        message_type: str = "broadcast",
    ) -> None:
        """Persist a message in the MessageBus. Never raises."""
        try:
            await _send_bus_message(
                to_agent_id=to_agent_id,
                subject=subject,
                content=content,
                payload=payload,
                priority=priority,
                message_type=message_type,
            )
        except Exception as e:
            logger.warning(
                "MessageBus send failed to %s: %s", to_agent_id, e
            )


# =============================================================================
# Module-level singleton
# =============================================================================

agent_event_bridge = AgentEventBridge()
