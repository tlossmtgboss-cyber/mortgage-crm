"""
Infrastructure Agents

System health and maintenance autonomous agents:
1. database_cleanup — Daily, archive old data, clean orphan records
2. api_health_checker — Every 5 min, verify external API integrations
3. token_refresh — Every 15 min, refresh expiring OAuth tokens
4. log_aggregation — Every 4 hours, aggregate agent performance metrics
5. cost_optimization — Daily, track AI token usage and optimize spend
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Database Cleanup Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="database_cleanup",
    description="Archive old data, clean orphan records, maintain DB health",
    frequency=AgentFrequency.DAILY_6AM,
    max_runtime_seconds=120,
)
def database_cleanup(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Clean up stale data: old notifications, orphan tasks, expired sessions."""
    actions = 0

    # Archive old read notifications (90+ days)
    deleted_notif = db.execute(text("""
        DELETE FROM notifications
        WHERE organization_id = :org_id AND is_read = true
          AND created_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id})
    actions += deleted_notif.rowcount or 0

    # Clean completed tasks older than 180 days
    archived_tasks = db.execute(text("""
        UPDATE tasks SET status = 'archived'
        WHERE organization_id = :org_id AND status = 'completed'
          AND updated_at < CURRENT_TIMESTAMP - INTERVAL '180 days'
          AND status != 'archived'
    """), {"org_id": organization_id})
    actions += archived_tasks.rowcount or 0

    # Clean old agent execution logs (60+ days)
    cleaned_runs = db.execute(text("""
        DELETE FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND started_at < CURRENT_TIMESTAMP - INTERVAL '60 days'
    """), {"org_id": organization_id})
    actions += cleaned_runs.rowcount or 0

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database cleanup commit failed: {e}")

    return {
        "summary": f"Cleaned {actions} stale records",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. API Health Checker
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="api_health_checker",
    description="Verify all external API integrations are responsive",
    frequency=AgentFrequency.EVERY_5_MIN,
    max_runtime_seconds=30,
)
def api_health_checker(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check connectivity to external services and log any failures."""
    actions = 0
    checks = {}

    # Check if org has active integrations
    integrations = db.execute(text("""
        SELECT provider, status, last_sync_at FROM oauth_tokens
        WHERE organization_id = :org_id AND is_active = true
    """), {"org_id": organization_id}).fetchall()

    for integration in integrations:
        provider = integration[0]
        status = integration[1]
        last_sync = integration[2]

        # Flag integrations in error state
        if status == 'error':
            checks[provider] = "ERROR"
            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE title LIKE :pattern AND organization_id = :org_id
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '6 hours'
                LIMIT 1
            """), {"pattern": f"%{provider}%health%", "org_id": organization_id}).fetchone()

            if not existing:
                db.execute(text("""
                    INSERT INTO tasks (title, description, priority, status,
                                       due_date, created_at, organization_id)
                    VALUES (:title, :desc, 'high', 'pending',
                            CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "title": f"Integration health: {provider} in error state",
                    "desc": f"{provider} integration is in error state. Last sync: {last_sync}. Check credentials and reconnect.",
                    "org_id": organization_id,
                })
                actions += 1
        else:
            checks[provider] = "OK"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"API health check commit failed: {e}")

    return {
        "summary": f"Checked {len(integrations)} integrations, {actions} alerts",
        "actions_taken": actions,
        "notifications_sent": 0,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Token Refresh Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="token_refresh",
    description="Refresh expiring OAuth tokens before they expire",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def token_refresh(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find OAuth tokens expiring in the next 10 minutes and refresh them."""
    actions = 0

    expiring = db.execute(text("""
        SELECT id, provider, user_id, refresh_token
        FROM oauth_tokens
        WHERE organization_id = :org_id
          AND is_active = true
          AND token_expires_at IS NOT NULL
          AND token_expires_at < CURRENT_TIMESTAMP + INTERVAL '10 minutes'
          AND token_expires_at > CURRENT_TIMESTAMP
          AND refresh_token IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    for token in expiring:
        provider = token[1]
        try:
            if provider == 'microsoft':
                # Delegate to Graph refresh logic
                from services.dre_helpers import refresh_microsoft_token
                success = refresh_microsoft_token(db, token[2])
                if success:
                    actions += 1
                    logger.info(f"Refreshed Microsoft token for user {token[2]}")
            elif provider == 'salesforce':
                # Salesforce tokens don't auto-refresh; mark for re-auth
                db.execute(text("""
                    UPDATE oauth_tokens SET status = 'expired'
                    WHERE id = :id
                """), {"id": token[0]})
                actions += 1
        except Exception as e:
            logger.warning(f"Token refresh failed for {provider} user {token[2]}: {e}")
            db.execute(text("""
                UPDATE oauth_tokens SET status = 'error'
                WHERE id = :id
            """), {"id": token[0]})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Token refresh commit failed: {e}")

    return {
        "summary": f"Refreshed {actions} tokens, {len(expiring)} expiring",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Log Aggregation Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="log_aggregation",
    description="Aggregate agent performance metrics for monitoring",
    frequency=AgentFrequency.EVERY_4_HOURS,
    max_runtime_seconds=60,
)
def log_aggregation(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Summarize autonomous agent performance over the last 4 hours."""

    stats = db.execute(text("""
        SELECT agent_name,
               COUNT(*) as runs,
               COUNT(CASE WHEN success THEN 1 END) as successes,
               SUM(actions_taken) as total_actions,
               SUM(notifications_sent) as total_notifs,
               AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_s
        FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND started_at >= CURRENT_TIMESTAMP - INTERVAL '4 hours'
        GROUP BY agent_name
        ORDER BY runs DESC
    """), {"org_id": organization_id}).fetchall()

    lines = []
    for s in stats:
        fail_rate = ((s[1] - s[2]) / s[1] * 100) if s[1] else 0
        lines.append(f"{s[0]}: {s[1]} runs ({s[2]} ok), {s[3] or 0} actions, {float(s[5] or 0):.1f}s avg")
        if fail_rate > 50:
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status,
                                   due_date, created_at, organization_id)
                VALUES (:title, :desc, 'high', 'pending',
                        CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Agent health: {s[0]} failing {fail_rate:.0f}% of runs",
                "desc": f"Agent {s[0]} failed {s[1] - s[2]}/{s[1]} runs in last 4 hours. Investigate errors.",
                "org_id": organization_id,
            })

    summary = "; ".join(lines[:5]) if lines else "No agent runs in last 4 hours"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Log aggregation commit failed: {e}")

    return {
        "summary": summary,
        "actions_taken": len(stats),
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Cost Optimization Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="cost_optimization",
    description="Track AI token usage and identify cost optimization opportunities",
    frequency=AgentFrequency.DAILY_6PM,
    max_runtime_seconds=60,
)
def cost_optimization(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Analyze AI usage patterns and flag high-cost operations."""
    actions = 0

    # Check agent invocation costs (if tracking table exists)
    try:
        usage = db.execute(text("""
            SELECT
                COUNT(*) as total_invocations,
                SUM(tokens_input + tokens_output) as total_tokens,
                AVG(tokens_input + tokens_output) as avg_tokens,
                MAX(tokens_input + tokens_output) as max_tokens
            FROM agent_invocations
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
        """), {"org_id": organization_id}).fetchone()

        if usage and usage[0]:
            total_tokens = int(usage[1] or 0)
            # Rough cost estimate: $3/MTok input, $15/MTok output (Sonnet pricing)
            est_cost = total_tokens / 1_000_000 * 5  # blended rate

            summary = (
                f"Daily AI usage: {usage[0]} invocations, {total_tokens:,} tokens, "
                f"avg {int(usage[2] or 0):,}/req, est ${est_cost:.2f}"
            )

            if est_cost > 10:  # Flag if daily cost exceeds $10
                db.execute(text("""
                    INSERT INTO tasks (title, description, priority, status,
                                       due_date, created_at, organization_id)
                    VALUES ('AI cost alert: $' || :cost || ' today', :desc,
                            'medium', 'pending', CURRENT_DATE + 1, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "cost": f"{est_cost:.2f}",
                    "desc": f"AI token spend estimated at ${est_cost:.2f} today ({total_tokens:,} tokens across {usage[0]} invocations). Review for optimization.",
                    "org_id": organization_id,
                })
                actions += 1
        else:
            summary = "No AI invocations tracked today"

    except Exception:
        summary = "Agent invocation tracking table not available"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Cost optimization commit failed: {e}")

    return {
        "summary": summary,
        "actions_taken": actions,
        "notifications_sent": 0,
    }
