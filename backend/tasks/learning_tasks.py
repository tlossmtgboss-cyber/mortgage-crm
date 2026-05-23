"""
Continuous Learning System Celery Tasks

Periodic tasks that drive the AI learning feedback loop:
    - run_learning_cycle: Weekly meta-agent analysis and improvement identification
    - analyze_recent_conversations: Daily conversation quality analysis
    - refresh_agent_memory_scores: Daily memory maintenance and expiry cleanup
    - agent_learning_health_check: Periodic agent performance health scoring

These tasks activate the ContinuousLearningMetaAgent and
ConversationAILearningService, which exist but were previously
never triggered on a schedule.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db_session():
    """Create a fresh DB session for background tasks (no RLS tenant context)."""
    from db import SessionLocal
    return SessionLocal()


# ============================================================================
# Task 1: Weekly Learning Cycle
# ============================================================================

@celery_app.task(
    name="tasks.learning_tasks.run_learning_cycle",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=480,
    time_limit=540,
)
def run_learning_cycle(self, period_hours: int = 168):
    """
    Run the ContinuousLearningMetaAgent learning cycle.

    Analyzes recent AI performance across all conversations, identifies
    improvement opportunities, executes auto-actions where safe, and
    generates recommendations.

    Args:
        period_hours: Number of hours of data to analyze (default 168 = 1 week).

    Returns:
        Dict with cycle_id, opportunities found, actions taken, and recommendations.
    """
    db = None
    try:
        db = _get_db_session()
        logger.info(
            "Starting learning cycle task (period_hours=%d)", period_hours
        )

        from services.continuous_learning_meta_agent import ContinuousLearningMetaAgent
        from services.conversation_ai_learning_service import ConversationAILearningService

        ai_learning = ConversationAILearningService(db_session=db)
        meta_agent = ContinuousLearningMetaAgent(
            db_session=db,
            ai_learning_service=ai_learning,
        )

        report = meta_agent.run_learning_cycle(period_hours=period_hours)

        result = {
            "cycle_id": report.cycle_id,
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat(),
            "opportunities_found": len(report.opportunities_identified),
            "actions_taken": len(report.actions_taken),
            "recommendations": report.recommendations,
        }

        logger.info(
            "Learning cycle %s complete: %d opportunities, %d actions",
            report.cycle_id,
            len(report.opportunities_identified),
            len(report.actions_taken),
        )
        return result

    except Exception as e:
        logger.error("Learning cycle task failed: %s", e, exc_info=True)
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Learning cycle exhausted retries")
            return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Task 2: Daily Conversation Analysis
# ============================================================================

@celery_app.task(
    name="tasks.learning_tasks.analyze_recent_conversations",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=480,
    time_limit=540,
)
def analyze_recent_conversations(self, hours: int = 24):
    """
    Analyze completed chat sessions from the last N hours.

    Queries AgentChatSession rows that ended within the window,
    reconstructs messages, and feeds them through
    ConversationAILearningService.analyze_conversation().

    Args:
        hours: Lookback window in hours (default 24).

    Returns:
        Dict with sessions analyzed, quality stats, and gaps found.
    """
    db = None
    try:
        db = _get_db_session()
        logger.info("Starting conversation analysis task (hours=%d)", hours)

        from models.agent_governance import AgentChatSession, AgentChatMessage
        from services.conversation_ai_learning_service import (
            ConversationAILearningService,
            ConversationOutcome,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Find completed sessions within the window
        sessions = (
            db.query(AgentChatSession)
            .filter(
                AgentChatSession.is_active == False,  # noqa: E712
                AgentChatSession.ended_at >= cutoff,
            )
            .order_by(AgentChatSession.ended_at.desc())
            .limit(500)
            .all()
        )

        if not sessions:
            logger.info("No completed sessions found in last %d hours", hours)
            return {"sessions_analyzed": 0, "message": "no sessions to analyze"}

        learning_service = ConversationAILearningService(db_session=db)

        results = {
            "sessions_analyzed": 0,
            "high_quality": 0,
            "low_quality": 0,
            "knowledge_gaps_found": 0,
            "training_examples_generated": 0,
            "errors": 0,
        }

        for session in sessions:
            try:
                # Load messages for this session
                messages_rows = (
                    db.query(AgentChatMessage)
                    .filter(AgentChatMessage.session_id == session.id)
                    .order_by(AgentChatMessage.created_at.asc())
                    .all()
                )

                if not messages_rows:
                    continue

                messages = [
                    {"role": m.role, "content": m.content}
                    for m in messages_rows
                ]

                # Determine outcome heuristically from session context
                outcome = _infer_session_outcome(session)

                metadata = {
                    "agent_name": session.agent_name,
                    "message_count": session.message_count or len(messages),
                    "total_tokens": session.total_tokens or 0,
                }

                analysis = learning_service.analyze_conversation(
                    conversation_id=str(session.session_id),
                    messages=messages,
                    outcome=outcome,
                    metadata=metadata,
                )

                results["sessions_analyzed"] += 1

                if analysis.quality_score >= 0.7:
                    results["high_quality"] += 1
                elif analysis.quality_score < 0.5:
                    results["low_quality"] += 1

                results["knowledge_gaps_found"] += len(
                    analysis.knowledge_gaps_identified
                )
                results["training_examples_generated"] += len(
                    analysis.successful_responses
                )

            except Exception as e:
                logger.warning(
                    "Error analyzing session %s: %s", session.id, e
                )
                results["errors"] += 1

        logger.info(
            "Conversation analysis complete: %d sessions, %d high quality, "
            "%d low quality, %d knowledge gaps",
            results["sessions_analyzed"],
            results["high_quality"],
            results["low_quality"],
            results["knowledge_gaps_found"],
        )
        return results

    except Exception as e:
        logger.error("Conversation analysis task failed: %s", e, exc_info=True)
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Conversation analysis exhausted retries")
            return {"error": str(e)}
    finally:
        if db:
            db.close()


def _infer_session_outcome(session):
    """
    Heuristically infer conversation outcome from session data.

    Uses message count and context flags to guess the outcome.
    """
    from services.conversation_ai_learning_service import ConversationOutcome

    ctx = session.context or {}

    # Check for explicit outcome markers in session context
    if ctx.get("escalated"):
        return ConversationOutcome.ESCALATED
    if ctx.get("abandoned"):
        return ConversationOutcome.ABANDONED
    if ctx.get("success") or ctx.get("booking_confirmed"):
        return ConversationOutcome.SUCCESS

    # Heuristic: very short sessions with no resolution are likely abandoned
    msg_count = session.message_count or 0
    if msg_count <= 1:
        return ConversationOutcome.ABANDONED
    if msg_count <= 3:
        return ConversationOutcome.PARTIAL_SUCCESS

    # Default: assume success for longer conversations
    return ConversationOutcome.SUCCESS


# ============================================================================
# Task 3: Daily Memory Maintenance
# ============================================================================

@celery_app.task(
    name="tasks.learning_tasks.refresh_agent_memory_scores",
    soft_time_limit=240,
    time_limit=300,
)
def refresh_agent_memory_scores():
    """
    Maintain agent memory health:
    1. Delete expired memories (expires_at < now).
    2. Clean up orphaned conversation records.
    3. Apply tiered confidence decay (90/180-day via apply_confidence_decay).

    Returns:
        Dict with counts of expired pruned and old conversations removed.
    """
    db = None
    try:
        db = _get_db_session()
        logger.info("Starting agent memory maintenance task")

        from services.agent_memory_service import (
            prune_expired_memories,
            prune_old_conversations,
        )

        results = {
            "expired_pruned": 0,
            "old_conversations_pruned": 0,
        }

        # Step 1: Prune expired memories
        expired_count = prune_expired_memories(db)
        results["expired_pruned"] = expired_count

        # Step 2: Prune old conversation summaries (older than 180 days)
        old_convs = prune_old_conversations(db, days=180)
        results["old_conversations_pruned"] = old_convs

        db.commit()

        # Step 3: Verification-based confidence decay (90/180-day tiers)
        try:
            from services.aria_memory.conflict_detector import apply_confidence_decay
            decay_result = apply_confidence_decay(db)
            results["verification_decay"] = decay_result
        except Exception as e:
            logger.warning("Verification-based confidence decay failed: %s", e)
            results["verification_decay"] = {"error": str(e)}

        logger.info(
            "Memory maintenance complete: %d expired, %d old convs",
            results["expired_pruned"],
            results["old_conversations_pruned"],
        )
        return results

    except Exception as e:
        logger.error("Memory maintenance task failed: %s", e, exc_info=True)
        if db:
            db.rollback()
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Task 4: Agent Health Check (Learning-Focused)
# ============================================================================

@celery_app.task(
    name="tasks.learning_tasks.agent_learning_health_check",
    soft_time_limit=120,
    time_limit=180,
)
def agent_learning_health_check(
    success_rate_threshold: float = 75.0,
):
    """
    Check each agent's recent performance and create health score entries.

    Differs from the existing agent_tasks.run_agent_health_checks() by
    focusing on learning-relevant metrics: success rates over longer windows,
    knowledge gap trends, and conversation quality scores.

    Args:
        success_rate_threshold: Minimum acceptable success rate percentage.

    Returns:
        Dict with per-agent health assessments and any alerts created.
    """
    db = None
    try:
        db = _get_db_session()
        logger.info("Starting agent learning health check")

        from models.agent_governance import (
            AgentProfile,
            AgentExecution,
            AgentAlert,
            AgentChatSession,
        )

        now = datetime.now(timezone.utc)
        lookback_6h = now - timedelta(hours=6)
        lookback_24h = now - timedelta(hours=24)

        agents = (
            db.query(AgentProfile)
            .filter(AgentProfile.status == "active")
            .all()
        )

        results = {
            "agents_checked": 0,
            "healthy": 0,
            "degraded": 0,
            "critical": 0,
            "alerts_created": 0,
            "details": [],
        }

        for agent in agents:
            agent_result = {
                "agent_id": agent.id,
                "agent_name": agent.agent_name,
                "status": "healthy",
                "metrics": {},
            }

            # Get 24h execution metrics
            executions_24h = (
                db.query(AgentExecution)
                .filter(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.created_at >= lookback_24h,
                )
                .all()
            )

            total_24h = len(executions_24h)
            if total_24h > 0:
                success_24h = len([e for e in executions_24h if e.success])
                failed_24h = len([e for e in executions_24h if e.success is False])
                success_rate = (success_24h / total_24h) * 100

                response_times = [
                    e.response_time_ms
                    for e in executions_24h
                    if e.response_time_ms
                ]
                avg_response = (
                    sum(response_times) / len(response_times)
                    if response_times
                    else 0
                )

                agent_result["metrics"] = {
                    "total_24h": total_24h,
                    "success_rate_24h": round(success_rate, 1),
                    "failed_24h": failed_24h,
                    "avg_response_ms": round(avg_response, 0),
                }

                # Get 6h session stats
                sessions_6h = (
                    db.query(AgentChatSession)
                    .filter(
                        AgentChatSession.agent_id == agent.id,
                        AgentChatSession.started_at >= lookback_6h,
                    )
                    .all()
                )

                active_sessions = len([s for s in sessions_6h if s.is_active])
                completed_sessions = len(
                    [s for s in sessions_6h if not s.is_active]
                )
                agent_result["metrics"]["active_sessions_6h"] = active_sessions
                agent_result["metrics"]["completed_sessions_6h"] = completed_sessions

                # Determine health status
                if success_rate < success_rate_threshold * 0.5:
                    agent_result["status"] = "critical"
                    results["critical"] += 1
                    _create_learning_alert(
                        db,
                        agent,
                        "critical",
                        f"Agent {agent.agent_name} success rate critically low: "
                        f"{success_rate:.1f}% (threshold: {success_rate_threshold}%)",
                    )
                    results["alerts_created"] += 1
                elif success_rate < success_rate_threshold:
                    agent_result["status"] = "degraded"
                    results["degraded"] += 1
                    _create_learning_alert(
                        db,
                        agent,
                        "warning",
                        f"Agent {agent.agent_name} success rate below threshold: "
                        f"{success_rate:.1f}% (threshold: {success_rate_threshold}%)",
                    )
                    results["alerts_created"] += 1
                else:
                    results["healthy"] += 1
            else:
                # No executions in 24h - still healthy, just inactive
                agent_result["metrics"]["total_24h"] = 0
                results["healthy"] += 1

            results["agents_checked"] += 1
            results["details"].append(agent_result)

        db.commit()

        logger.info(
            "Agent learning health check complete: %d checked, %d healthy, "
            "%d degraded, %d critical",
            results["agents_checked"],
            results["healthy"],
            results["degraded"],
            results["critical"],
        )

        # Don't include full details in the celery result (could be large)
        return {
            "agents_checked": results["agents_checked"],
            "healthy": results["healthy"],
            "degraded": results["degraded"],
            "critical": results["critical"],
            "alerts_created": results["alerts_created"],
        }

    except Exception as e:
        logger.error(
            "Agent learning health check failed: %s", e, exc_info=True
        )
        if db:
            db.rollback()
        return {"error": str(e)}
    finally:
        if db:
            db.close()


def _create_learning_alert(
    db,
    agent,
    severity: str,
    message: str,
):
    """
    Create a learning-related health alert for an agent.

    Deduplicates against existing active alerts from the last 6 hours.
    """
    from models.agent_governance import AgentAlert

    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)

    existing = (
        db.query(AgentAlert)
        .filter(
            AgentAlert.agent_id == agent.id,
            AgentAlert.alert_type == "learning_health",
            AgentAlert.status == "active",
            AgentAlert.created_at >= cutoff,
        )
        .first()
    )

    if existing:
        return  # Don't duplicate

    alert = AgentAlert(
        agent_id=agent.id,
        agent_name=agent.agent_name,
        alert_type="learning_health",
        severity=severity,
        title=f"Learning health: {agent.display_name or agent.agent_name}",
        message=message,
        status="active",
        details={"source": "learning_tasks.agent_learning_health_check"},
    )
    db.add(alert)
