"""
Agent Message Processor

Background task that polls the ``ai_agent_messages`` table for unprocessed
messages, routes each to the appropriate agent handler, and marks them as
processed afterward.

Designed to run:
  - As an APScheduler job (every 5 minutes) via ``register_message_processor_job``
  - On demand via ``process_pending_messages()``

All operations are fault-tolerant: a single bad message never blocks the rest.

Usage (in scheduler_service.py or main.py startup):
    from services.agent_message_processor import register_message_processor_job
    register_message_processor_job(scheduler)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# Agent handler registry
# =============================================================================

# Maps agent IDs to handler callables.  Each handler receives
# (message_id, subject, content, payload) and returns True on success.
# Handlers are registered lazily to avoid circular imports.

_AGENT_HANDLERS: Dict[str, Any] = {}
_HANDLERS_INITIALIZED = False


def _ensure_handlers():
    """Register agent message handlers (lazy, one-time)."""
    global _HANDLERS_INITIALIZED
    if _HANDLERS_INITIALIZED:
        return
    _HANDLERS_INITIALIZED = True

    # Each handler logs what it received and performs lightweight triage.
    # Heavy processing (LLM calls, tool execution) is deferred to the agent's
    # own orchestration loop -- the handler here only creates a task or
    # queues work for that agent.

    def _handle_pipeline_message(message_id, subject, content, payload):
        """Pipeline Analyst: log the inbound signal for the next sweep."""
        logger.info(
            "[MSG-PROCESSOR] pipeline_analyst received: %s (msg=%s)",
            subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="pipeline_analyst",
            title=subject,
            description=content,
            payload=payload,
        )
        return True

    def _handle_compliance_message(message_id, subject, content, payload):
        """Compliance Checker: triage violation severity and log."""
        severity = payload.get("severity", "medium")
        logger.info(
            "[MSG-PROCESSOR] compliance_checker received [%s]: %s (msg=%s)",
            severity, subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="compliance_checker",
            title=subject,
            description=content,
            payload=payload,
            priority="high" if severity in ("critical", "high") else "medium",
        )
        return True

    def _handle_lead_message(message_id, subject, content, payload):
        """Lead Nurturer: queue follow-up action."""
        logger.info(
            "[MSG-PROCESSOR] lead_nurturer received: %s (msg=%s)",
            subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="lead_nurturer",
            title=subject,
            description=content,
            payload=payload,
        )
        return True

    def _handle_document_message(message_id, subject, content, payload):
        """Document Tracker: queue doc review."""
        logger.info(
            "[MSG-PROCESSOR] document_tracker received: %s (msg=%s)",
            subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="document_tracker",
            title=subject,
            description=content,
            payload=payload,
        )
        return True

    def _handle_customer_message(message_id, subject, content, payload):
        """Customer Intelligence: queue outreach."""
        logger.info(
            "[MSG-PROCESSOR] customer_intelligence received: %s (msg=%s)",
            subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="customer_intelligence",
            title=subject,
            description=content,
            payload=payload,
        )
        return True

    def _handle_ops_message(message_id, subject, content, payload):
        """Ops Manager: queue escalation."""
        logger.info(
            "[MSG-PROCESSOR] ops_manager received: %s (msg=%s)",
            subject, message_id,
        )
        _create_agent_task_if_needed(
            agent_id="ops_manager",
            title=subject,
            description=content,
            payload=payload,
            priority="high",
        )
        return True

    _AGENT_HANDLERS["pipeline_analyst"] = _handle_pipeline_message
    _AGENT_HANDLERS["compliance_checker"] = _handle_compliance_message
    _AGENT_HANDLERS["lead_nurturer"] = _handle_lead_message
    _AGENT_HANDLERS["document_tracker"] = _handle_document_message
    _AGENT_HANDLERS["customer_intelligence"] = _handle_customer_message
    _AGENT_HANDLERS["ops_manager"] = _handle_ops_message

    logger.info(
        "[MSG-PROCESSOR] Registered %d agent message handlers", len(_AGENT_HANDLERS)
    )


def _create_agent_task_if_needed(
    agent_id: str,
    title: str,
    description: str,
    payload: Dict[str, Any],
    priority: str = "medium",
) -> None:
    """Create a record in ai_tasks so the agent picks it up on its next cycle.

    Uses dedup: if an identical open task already exists, skip creation.
    Fails silently if the table is unavailable.
    """
    try:
        from database import SessionLocal
        session = SessionLocal()
        try:
            # Dedup check
            existing = session.execute(
                text(
                    "SELECT id FROM ai_tasks "
                    "WHERE title = :title "
                    "AND type::text NOT ILIKE '%completed%' "
                    "LIMIT 1"
                ),
                {"title": title},
            ).fetchone()

            if existing:
                return

            # Resolve tasktype enum
            task_type = None
            try:
                rows = session.execute(
                    text("SELECT unnest(enum_range(NULL::tasktype)) as val")
                ).fetchall()
                for r in rows:
                    if r[0].lower().replace("_", " ") == "human needed":
                        task_type = r[0]
                        break
                if not task_type and rows:
                    task_type = rows[0][0]
            except Exception:
                pass

            cols = ["title", "description", "priority", "category", "created_at"]
            vals = [":title", ":description", ":priority", ":category", "NOW()"]
            params: Dict[str, Any] = {
                "title": title[:500],
                "description": (description or "")[:2000],
                "priority": priority,
                "category": f"AGENT_{agent_id.upper()}",
            }

            if task_type:
                cols.append("type")
                vals.append("CAST(:task_type AS tasktype)")
                params["task_type"] = task_type

            loan_id = payload.get("loan_id")
            if loan_id:
                cols.append("loan_id")
                vals.append(":loan_id")
                params["loan_id"] = loan_id

            lead_id = payload.get("lead_id")
            if lead_id:
                cols.append("lead_id")
                vals.append(":lead_id")
                params["lead_id"] = lead_id

            session.execute(
                text(f"INSERT INTO ai_tasks ({', '.join(cols)}) VALUES ({', '.join(vals)})"),
                params,
            )
            session.commit()
            logger.debug("[MSG-PROCESSOR] Created ai_task: %s", title[:80])
        except SQLAlchemyError as e:
            session.rollback()
            logger.warning("[MSG-PROCESSOR] Failed to create ai_task: %s", e)
        finally:
            session.close()
    except Exception as e:
        logger.debug("[MSG-PROCESSOR] ai_task creation skipped: %s", e)


# =============================================================================
# Core processing function
# =============================================================================

def process_pending_messages(batch_size: int = 50) -> Dict[str, int]:
    """Poll ``ai_agent_messages`` for pending messages and route them.

    Returns a summary dict: {processed, failed, skipped}.
    """
    _ensure_handlers()

    stats = {"processed": 0, "failed": 0, "skipped": 0}

    try:
        from database import SessionLocal
    except ImportError:
        logger.debug("[MSG-PROCESSOR] database module unavailable, skipping")
        return stats

    session = SessionLocal()
    try:
        # Fetch pending messages ordered by priority then creation time
        rows = session.execute(
            text("""
                SELECT
                    id, message_id, from_agent_id, to_agent_id,
                    message_type, subject, content, payload, priority
                FROM ai_agent_messages
                WHERE status = 'pending'
                ORDER BY
                    CASE priority
                        WHEN 'urgent' THEN 1
                        WHEN 'high'   THEN 2
                        WHEN 'normal' THEN 3
                        WHEN 'low'    THEN 4
                        ELSE 5
                    END,
                    created_at ASC
                LIMIT :limit
            """),
            {"limit": batch_size},
        ).fetchall()

        if not rows:
            return stats

        logger.info("[MSG-PROCESSOR] Processing %d pending messages", len(rows))

        for row in rows:
            msg_id = row[1]  # message_id
            to_agent = row[3]  # to_agent_id
            subject = row[5] or ""
            content = row[6] or ""
            raw_payload = row[7]

            # Parse payload
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except (json.JSONDecodeError, TypeError):
                    payload = {}
            elif isinstance(raw_payload, dict):
                payload = raw_payload
            else:
                payload = {}

            # Route to handler
            handler = _AGENT_HANDLERS.get(to_agent)
            if handler is None:
                # Broadcast messages (to_agent_id IS NULL) go to all handlers
                if to_agent is None:
                    for agent_id, h in _AGENT_HANDLERS.items():
                        try:
                            h(msg_id, subject, content, payload)
                        except Exception as e:
                            logger.warning(
                                "[MSG-PROCESSOR] Broadcast handler %s failed for msg %s: %s",
                                agent_id, msg_id, e,
                            )
                else:
                    logger.debug(
                        "[MSG-PROCESSOR] No handler for agent %s, skipping msg %s",
                        to_agent, msg_id,
                    )
                    stats["skipped"] += 1
                    # Still mark as processed to avoid infinite retry
                    _mark_processed(session, msg_id)
                    continue

            try:
                if handler:
                    handler(msg_id, subject, content, payload)
                _mark_processed(session, msg_id)
                stats["processed"] += 1
            except Exception as e:
                logger.error(
                    "[MSG-PROCESSOR] Failed to process message %s: %s",
                    msg_id, e, exc_info=True,
                )
                _mark_failed(session, msg_id, str(e))
                stats["failed"] += 1

        session.commit()

    except SQLAlchemyError as e:
        session.rollback()
        logger.error("[MSG-PROCESSOR] DB error during message processing: %s", e)
    except Exception as e:
        logger.error("[MSG-PROCESSOR] Unexpected error: %s", e, exc_info=True)
    finally:
        session.close()

    logger.info(
        "[MSG-PROCESSOR] Done: %d processed, %d failed, %d skipped",
        stats["processed"], stats["failed"], stats["skipped"],
    )
    return stats


def _mark_processed(session, message_id: str) -> None:
    """Mark a message as processed."""
    try:
        session.execute(
            text(
                "UPDATE ai_agent_messages SET status = 'processed' "
                "WHERE message_id = :mid"
            ),
            {"mid": message_id},
        )
    except Exception as e:
        logger.warning("[MSG-PROCESSOR] Could not mark %s processed: %s", message_id, e)


def _mark_failed(session, message_id: str, error: str) -> None:
    """Mark a message as failed (keeps it from being retried immediately)."""
    try:
        session.execute(
            text(
                "UPDATE ai_agent_messages SET status = 'failed' "
                "WHERE message_id = :mid"
            ),
            {"mid": message_id},
        )
    except Exception as e:
        logger.warning("[MSG-PROCESSOR] Could not mark %s failed: %s", message_id, e)


# =============================================================================
# APScheduler integration
# =============================================================================

def register_message_processor_job(scheduler) -> None:
    """Register the message processor as a recurring APScheduler job.

    Runs every 5 minutes at :02, :07, :12, ... (offset from :00 to avoid
    contention with other scheduled jobs).

    Args:
        scheduler: An APScheduler BackgroundScheduler instance.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        func=process_pending_messages,
        trigger=IntervalTrigger(minutes=5),
        id="agent_message_processor",
        name="Process Pending Agent Messages",
        replace_existing=True,
    )
    logger.info("[MSG-PROCESSOR] Registered APScheduler job (every 5 min)")
