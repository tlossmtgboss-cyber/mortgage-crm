"""
AgentLearningMiddleware — Hot-path learning for continual improvement (Domain 8).

Captures user corrections, approvals, and overrides to AI agent outputs in
real time, writing to the ``agent_context_events`` table.  The consolidation
job reads these events later and folds them into the agent context store.

Usage:
    from middleware.learning_middleware import learning_middleware

    event = await learning_middleware.capture_correction(
        agent_id="document_tracker",
        user_id=42,
        file_id=10001,
        original_output={"condition": "VOE required"},
        corrected_value={"condition": "VOE not required — self-employed"},
        rationale="Borrower is 1099, VOE does not apply.",
        db=db,
    )
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentLearningMiddleware:
    """Captures corrections and approvals for continual learning hot-path."""

    # ------------------------------------------------------------------
    # Corrections — user modifies AI output before submitting
    # ------------------------------------------------------------------

    async def capture_correction(
        self,
        agent_id: str,
        user_id: int,
        file_id: int,
        original_output: dict,
        corrected_value: dict,
        rationale: str = None,
        db: Session = None,
    ) -> dict:
        """Record when a user modifies an AI agent output before submitting.

        This is the strongest learning signal — it means the agent was wrong
        and the LO knew the right answer.
        """
        event = self._build_event(
            agent_id=agent_id,
            user_id=user_id,
            file_id=file_id,
            event_type="correction",
            original_output=original_output,
            corrected_value=corrected_value,
            rationale=rationale,
        )
        return await self._persist_event(event, db)

    # ------------------------------------------------------------------
    # Approvals — agent output used without modification (positive signal)
    # ------------------------------------------------------------------

    async def capture_approval(
        self,
        agent_id: str,
        user_id: int,
        file_id: int,
        output: dict,
        action: str,
        db: Session = None,
    ) -> dict:
        """Record when agent output is used without modification.

        This is an implicit positive signal — the LO accepted the AI result.

        Args:
            action: One of 'sent', 'submitted', 'saved', 'applied'.
        """
        valid_actions = {"sent", "submitted", "saved", "applied"}
        if action not in valid_actions:
            logger.warning(
                "capture_approval called with unknown action=%s for agent=%s; "
                "expected one of %s",
                action,
                agent_id,
                valid_actions,
            )

        event = self._build_event(
            agent_id=agent_id,
            user_id=user_id,
            file_id=file_id,
            event_type="approval",
            original_output=output,
            corrected_value={"action": action},
            rationale=None,
        )
        return await self._persist_event(event, db)

    # ------------------------------------------------------------------
    # Overrides — LO overrides an underwriter condition
    # ------------------------------------------------------------------

    async def capture_override(
        self,
        agent_id: str,
        user_id: int,
        file_id: int,
        original_condition: dict,
        override_action: str,
        rationale: str = None,
        db: Session = None,
    ) -> dict:
        """Record when the LO overrides an underwriter condition.

        Override events feed back into the compliance and document tracker
        agents so they learn which conditions are routinely challenged.
        """
        event = self._build_event(
            agent_id=agent_id,
            user_id=user_id,
            file_id=file_id,
            event_type="override",
            original_output=original_condition,
            corrected_value={"override_action": override_action},
            rationale=rationale,
        )
        return await self._persist_event(event, db)

    # ------------------------------------------------------------------
    # Query — recent events for the consolidation job
    # ------------------------------------------------------------------

    async def get_recent_events(
        self,
        agent_id: str,
        hours: int = 24,
        db: Session = None,
    ) -> list:
        """Return recent events for an agent (used by the consolidation job).

        Args:
            agent_id: The agent whose events to retrieve.
            hours: Look-back window in hours (default 24).
            db: Active SQLAlchemy session.

        Returns:
            List of event dicts ordered by ``created_at`` descending.
        """
        if db is None:
            logger.error("get_recent_events called without db session")
            return []

        try:
            result = db.execute(
                text(
                    "SELECT id, agent_id, user_id, file_id, event_type, "
                    "       original_output, corrected_value, rationale, created_at "
                    "FROM agent_context_events "
                    "WHERE agent_id = :agent_id "
                    "  AND created_at >= NOW() - INTERVAL ':hours hours' "
                    "ORDER BY created_at DESC"
                ),
                {"agent_id": agent_id, "hours": hours},
            )
            rows = result.mappings().all()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(
                "Failed to fetch recent events for agent=%s: %s",
                agent_id,
                e,
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_event(
        *,
        agent_id: str,
        user_id: int,
        file_id: int,
        event_type: str,
        original_output: dict,
        corrected_value: dict,
        rationale: str | None,
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "user_id": user_id,
            "file_id": file_id,
            "event_type": event_type,
            "original_output": original_output,
            "corrected_value": corrected_value,
            "rationale": rationale,
            "created_at": datetime.now(timezone.utc),
        }

    async def _persist_event(self, event: dict, db: Session | None) -> dict:
        """Insert into ``agent_context_events`` via raw SQL.

        Falls back to returning the in-memory dict if no session is provided
        (useful in tests and when the caller will persist separately).
        """
        if db is None:
            logger.warning(
                "No db session provided — event %s recorded in-memory only",
                event["id"],
            )
            return event

        try:
            db.execute(
                text(
                    "INSERT INTO agent_context_events "
                    "(id, agent_id, user_id, file_id, event_type, "
                    " original_output, corrected_value, rationale, created_at) "
                    "VALUES (:id, :agent_id, :user_id, :file_id, :event_type, "
                    "        CAST(:original_output AS jsonb), "
                    "        CAST(:corrected_value AS jsonb), "
                    "        :rationale, :created_at)"
                ),
                {
                    "id": event["id"],
                    "agent_id": event["agent_id"],
                    "user_id": event["user_id"],
                    "file_id": event["file_id"],
                    "event_type": event["event_type"],
                    "original_output": _json_dumps(event["original_output"]),
                    "corrected_value": _json_dumps(event["corrected_value"]),
                    "rationale": event["rationale"],
                    "created_at": event["created_at"],
                },
            )
            db.commit()
            logger.info(
                "Persisted %s event id=%s for agent=%s user=%s file=%s",
                event["event_type"],
                event["id"],
                event["agent_id"],
                event["user_id"],
                event["file_id"],
            )
        except Exception as e:
            logger.exception(
                "Failed to persist %s event for agent=%s: %s",
                event["event_type"],
                event["agent_id"],
                e,
            )
            db.rollback()

        return event


def _json_dumps(obj) -> str:
    """Serialize to JSON string for CAST to jsonb."""
    import json
    return json.dumps(obj, default=str)


# Singleton — importable by route handlers
learning_middleware = AgentLearningMiddleware()
