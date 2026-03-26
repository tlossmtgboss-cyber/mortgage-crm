"""
Workflow expiration service — expires stale voice workflows past their expires_at.

Standalone function that can be called from Celery tasks, APScheduler jobs,
or management commands. Complements the existing Celery task at
tasks/expire_voice_workflows.py by providing a lightweight, dependency-minimal
entry point.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Terminal states that should not be expired (already finished)
TERMINAL_STATES = frozenset({"completed", "expired", "cancelled", "failed"})


def expire_stale_workflows(db_session: Session) -> int:
    """
    Expire voice workflows that are past their expires_at timestamp.

    Queries voice_workflows WHERE state NOT IN terminal states AND expires_at < NOW().
    Updates each to state='expired' and sets updated_at=NOW().

    Args:
        db_session: An active SQLAlchemy session. Caller is responsible for
                    committing or rolling back after this function returns.

    Returns:
        Number of workflows expired.
    """
    from database.models.voice_workflow import VoiceWorkflow

    now = datetime.now(timezone.utc)

    stale = (
        db_session.query(VoiceWorkflow)
        .filter(
            VoiceWorkflow.expires_at.isnot(None),
            VoiceWorkflow.expires_at < now,
            VoiceWorkflow.state.notin_(list(TERMINAL_STATES)),
        )
        .all()
    )

    expired_count = 0
    for wf in stale:
        old_state = wf.state
        wf.state = "expired"
        wf.updated_at = now.replace(tzinfo=None)  # match model's naive UTC convention
        expired_count += 1
        logger.debug(
            "Expired workflow %d: %s -> expired (was expires_at=%s)",
            wf.id, old_state, wf.expires_at,
        )

    logger.info(
        "Workflow expiration sweep complete: %d workflow(s) expired out of %d stale",
        expired_count, len(stale),
    )

    return expired_count
