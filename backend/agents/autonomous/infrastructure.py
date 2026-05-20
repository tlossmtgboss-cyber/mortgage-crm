"""
Infrastructure Agents

System health and maintenance autonomous agents:
1. database_cleanup — Daily 6 AM, archive old data, clean orphan records, verify integrity
2. api_health_checker — Every 5 min, verify external API integrations, track health trends
3. token_refresh — Every 15 min, proactively refresh expiring OAuth tokens
4. log_aggregation — Every 4 hours, aggregate agent fleet performance analytics
5. cost_optimization — Daily 6 PM, track AI token usage, detect spend spikes, optimize
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_int(val, default: int = 0) -> int:
    """Safely coerce a DB value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    """Safely coerce a DB value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division avoiding ZeroDivisionError."""
    return (numerator / denominator) if denominator else default


def _pct(numerator: float, denominator: float) -> float:
    """Return percentage with one decimal, safe from divide-by-zero."""
    return round(_safe_div(numerator * 100, denominator), 1)


def _insert_activity(
    db: Session,
    organization_id: int,
    content: str,
    report_data: Optional[Dict[str, Any]] = None,
    gateway=None,
) -> None:
    """Insert a System activity with optional structured JSON in user_metadata."""
    params = {
        "content": content[:4000],
        "metadata": json.dumps(report_data) if report_data else None,
        "org_id": organization_id,
    }
    def _do():
        db.execute(text("""
            INSERT INTO activities (lead_id, type, content, user_metadata, created_at, organization_id)
            VALUES (NULL, 'System', :content, :metadata, CURRENT_TIMESTAMP, :org_id)
        """), params)
    if gateway:
        gateway.propose(
            "create_activity", _do,
            target_entity=None,
            target_id=None,
            description=content[:200],
            payload=params,
        )
    else:
        _do()


def _insert_task(
    db: Session,
    organization_id: int,
    title: str,
    description: str,
    priority: str = "medium",
    assigned_to_id: Optional[int] = None,
    due_days: int = 3,
    dedup_hours: int = 48,
    gateway=None,
) -> bool:
    """Insert a task with deduplication. Returns True if task was created."""
    existing = db.execute(text("""
        SELECT id FROM tasks
        WHERE organization_id = :org_id
          AND title = :title
          AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour' * :dedup_hours
        LIMIT 1
    """), {"org_id": organization_id, "title": title[:255], "dedup_hours": dedup_hours}).fetchone()

    if existing:
        return False

    params = {
        "title": title[:255],
        "desc": description[:2000],
        "priority": priority,
        "due_days": due_days,
        "owner_id": str(assigned_to_id) if assigned_to_id else None,
        "org_id": organization_id,
    }
    def _do():
        db.execute(text("""
            INSERT INTO tasks (title, description, priority, status, due_date,
                               owner_id, created_at, organization_id)
            VALUES (:title, :desc, :priority, 'pending',
                    CURRENT_DATE + :due_days, :owner_id, CURRENT_TIMESTAMP, :org_id)
        """), params)
    if gateway:
        gateway.propose(
            "create_task", _do,
            target_entity=None,
            target_id=None,
            description=title[:200],
            payload=params,
        )
    else:
        _do()
    return True


def _insert_notification(
    db: Session,
    organization_id: int,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    gateway=None,
) -> None:
    """Insert an in-app notification for a user."""
    params = {
        "uid": user_id,
        "org_id": organization_id,
        "type": notification_type,
        "title": title[:255],
        "message": message[:2000],
        "link": link,
    }
    def _do():
        db.execute(text("""
            INSERT INTO notifications (user_id, organization_id, type, title,
                                       message, link, is_read, created_at)
            VALUES (:uid, :org_id, :type, :title, :message, :link, false, NOW())
        """), params)
    if gateway:
        gateway.propose(
            "create_notification", _do,
            target_entity="user",
            target_id=str(user_id),
            description=title[:200],
            payload=params,
        )
    else:
        _do()


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
    gateway=None,
) -> Dict[str, Any]:
    """
    Smart data maintenance with detailed per-category metrics:
    - Archive read notifications older than 90 days
    - Clean completed+archived tasks older than 180 days
    - Purge old autonomous_agent_runs older than 60 days
    - Clean old System activities older than 120 days (preserve non-system)
    - Detect orphan tasks (lead_id/loan_id pointing to deleted records)
    - Create alert task if orphan count exceeds threshold
    """
    actions = 0
    notifications_sent = 0
    metrics: Dict[str, Any] = {}

    # ── 1. Archive read notifications (90+ days) ───────────────────────────
    result = db.execute(text("""
        DELETE FROM notifications
        WHERE organization_id = :org_id
          AND is_read = true
          AND created_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
    """), {"org_id": organization_id})
    notifs_deleted = _safe_int(result.rowcount)
    actions += notifs_deleted
    metrics["notifications_deleted"] = notifs_deleted

    # ── 2. Clean completed + archived tasks (180+ days) ────────────────────
    # Delete fully archived tasks; mark old completed ones as archived first
    result_archive = db.execute(text("""
        UPDATE tasks SET status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE organization_id = :org_id
          AND status = 'completed'
          AND updated_at < CURRENT_TIMESTAMP - INTERVAL '180 days'
    """), {"org_id": organization_id})
    tasks_archived = _safe_int(result_archive.rowcount)

    result_delete = db.execute(text("""
        DELETE FROM tasks
        WHERE organization_id = :org_id
          AND status = 'archived'
          AND updated_at < CURRENT_TIMESTAMP - INTERVAL '180 days'
    """), {"org_id": organization_id})
    tasks_deleted = _safe_int(result_delete.rowcount)
    actions += tasks_archived + tasks_deleted
    metrics["tasks_archived"] = tasks_archived
    metrics["tasks_deleted"] = tasks_deleted

    # ── 3. Purge old agent execution logs (60+ days) ──────────────────────
    result = db.execute(text("""
        DELETE FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND started_at < CURRENT_TIMESTAMP - INTERVAL '60 days'
    """), {"org_id": organization_id})
    runs_deleted = _safe_int(result.rowcount)
    actions += runs_deleted
    metrics["agent_runs_deleted"] = runs_deleted

    # ── 4. Clean old System activities (120+ days, preserve non-system) ────
    result = db.execute(text("""
        DELETE FROM activities
        WHERE organization_id = :org_id
          AND type = 'System'
          AND created_at < CURRENT_TIMESTAMP - INTERVAL '120 days'
    """), {"org_id": organization_id})
    activities_deleted = _safe_int(result.rowcount)
    actions += activities_deleted
    metrics["system_activities_deleted"] = activities_deleted

    # ── 5. Detect orphan tasks (referencing deleted leads/loans) ──────────
    orphan_lead_tasks = db.execute(text("""
        SELECT COUNT(*) FROM tasks t
        WHERE t.organization_id = :org_id
          AND t.lead_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.id = t.lead_id)
    """), {"org_id": organization_id}).scalar() or 0

    orphan_loan_tasks = db.execute(text("""
        SELECT COUNT(*) FROM tasks t
        WHERE t.organization_id = :org_id
          AND t.loan_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM loans ln WHERE ln.id = t.loan_id)
    """), {"org_id": organization_id}).scalar() or 0

    total_orphans = orphan_lead_tasks + orphan_loan_tasks
    metrics["orphan_tasks_lead"] = orphan_lead_tasks
    metrics["orphan_tasks_loan"] = orphan_loan_tasks
    metrics["orphan_tasks_total"] = total_orphans

    # Create alert if orphan count above threshold
    if total_orphans > 10:
        created = _insert_task(
            db, organization_id,
            title=f"Data integrity: {total_orphans} orphan tasks detected",
            description=(
                f"Database cleanup found {orphan_lead_tasks} tasks referencing deleted leads "
                f"and {orphan_loan_tasks} tasks referencing deleted loans. "
                f"Review and clean up these orphan records to maintain data integrity."
            ),
            priority="high",
            due_days=3,
            dedup_hours=24,
            gateway=gateway,
        )
        if created:
            actions += 1

    # ── 6. Record total space reclaimed ────────────────────────────────────
    total_rows_cleaned = notifs_deleted + tasks_deleted + runs_deleted + activities_deleted
    metrics["total_rows_cleaned"] = total_rows_cleaned

    # Audit trail
    _insert_activity(db, organization_id,
        content=(
            f"Database cleanup: {total_rows_cleaned} rows removed "
            f"(notifs={notifs_deleted}, tasks={tasks_deleted}, "
            f"runs={runs_deleted}, activities={activities_deleted}). "
            f"Orphan tasks: {total_orphans}."
        ),
        report_data={"agent": "database_cleanup", "metrics": metrics},
        gateway=gateway,
    )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database cleanup commit failed for org {organization_id}: {e}")
        raise

    return {
        "summary": (
            f"Cleaned {total_rows_cleaned} rows "
            f"(notifs={notifs_deleted}, tasks={tasks_deleted}, "
            f"runs={runs_deleted}, activities={activities_deleted}). "
            f"Orphans: {total_orphans}"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "metrics": metrics,
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
    gateway=None,
) -> Dict[str, Any]:
    """
    Integration health monitoring with per-provider scoring:
    - Check all active oauth_tokens for each provider
    - Detect error/expired status, past token_expires_at
    - Calculate health score per provider (healthy / total * 100)
    - Create reconnection tasks when provider drops below 80% health
    - Compare current state to last run for trend detection
    - Store summary as structured activity
    """
    actions = 0
    notifications_sent = 0

    # ── 1. Fetch all active integration tokens ─────────────────────────────
    tokens = db.execute(text("""
        SELECT id, provider, status, token_expires_at, user_id, last_sync_at
        FROM oauth_tokens
        WHERE organization_id = :org_id
          AND is_active = true
        ORDER BY provider, id
    """), {"org_id": organization_id}).fetchall()

    if not tokens:
        return {
            "summary": "No active integrations to monitor",
            "actions_taken": 0,
            "notifications_sent": 0,
            "metrics": {"providers": {}, "overall_health": 100.0},
        }

    # ── 2. Evaluate per-provider health ────────────────────────────────────
    # Group tokens by provider
    provider_tokens: Dict[str, List[Dict[str, Any]]] = {}
    for tok in tokens:
        provider = tok[1]
        if provider not in provider_tokens:
            provider_tokens[provider] = []
        provider_tokens[provider].append({
            "id": tok[0],
            "status": tok[2],
            "expires_at": tok[3],
            "user_id": tok[4],
            "last_sync": tok[5],
        })

    provider_scores: Dict[str, Dict[str, Any]] = {}
    unhealthy_providers: List[str] = []

    for provider, ptokens in provider_tokens.items():
        total = len(ptokens)
        healthy = 0
        error_count = 0
        expired_count = 0
        affected_users: List[int] = []

        for t in ptokens:
            is_healthy = True

            # Check status field
            if t["status"] in ("error", "expired", "revoked"):
                is_healthy = False
                if t["status"] == "error":
                    error_count += 1
                else:
                    expired_count += 1

            # Check if token_expires_at is in the past
            if t["expires_at"] is not None:
                past_check = db.execute(text("""
                    SELECT CASE WHEN :expires_at < CURRENT_TIMESTAMP THEN 1 ELSE 0 END
                """), {"expires_at": t["expires_at"]}).scalar()
                if past_check == 1:
                    is_healthy = False
                    expired_count += 1

            if is_healthy:
                healthy += 1
            else:
                affected_users.append(t["user_id"])

        health_score = _pct(healthy, total)
        provider_scores[provider] = {
            "total_tokens": total,
            "healthy": healthy,
            "error_count": error_count,
            "expired_count": expired_count,
            "health_score": health_score,
            "affected_user_ids": affected_users[:20],  # cap for storage
        }

        if health_score < 80.0:
            unhealthy_providers.append(provider)

    # ── 3. Load previous health scores from last run for trend detection ───
    previous_run = db.execute(text("""
        SELECT summary FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND agent_name = 'api_health_checker'
          AND success = true
        ORDER BY completed_at DESC
        LIMIT 1 OFFSET 1
    """), {"org_id": organization_id}).fetchone()

    trend_notes: List[str] = []
    if previous_run and previous_run[0]:
        # Try to extract provider names that were previously healthy but now degraded
        for provider in unhealthy_providers:
            if provider not in (previous_run[0] or ""):
                trend_notes.append(f"{provider} newly degraded")

    # ── 4. Create reconnection tasks for unhealthy providers ───────────────
    for provider in unhealthy_providers:
        score_info = provider_scores[provider]
        created = _insert_task(
            db, organization_id,
            title=f"Integration alert: {provider} at {score_info['health_score']}% health",
            description=(
                f"{provider} integration health dropped below 80%. "
                f"Healthy: {score_info['healthy']}/{score_info['total_tokens']} tokens. "
                f"Errors: {score_info['error_count']}, Expired: {score_info['expired_count']}. "
                f"Affected users: {len(score_info['affected_user_ids'])}. "
                f"Check credentials and reconnect affected accounts."
            ),
            priority="high",
            due_days=1,
            dedup_hours=6,  # Don't spam; re-alert after 6 hours if still bad
            gateway=gateway,
        )
        if created:
            actions += 1

        # Notify each affected user (up to 5 per provider per check)
        for user_id in score_info["affected_user_ids"][:5]:
            _insert_notification(
                db, organization_id, user_id,
                notification_type="integration_health",
                title=f"{provider.title()} integration needs attention",
                message=(
                    f"Your {provider} connection may be expired or in error. "
                    f"Please reconnect from Settings > Integrations."
                ),
                link="/settings/integrations",
                gateway=gateway,
            )
            notifications_sent += 1

    # ── 5. Calculate fleet-wide health score ───────────────────────────────
    total_all = sum(s["total_tokens"] for s in provider_scores.values())
    healthy_all = sum(s["healthy"] for s in provider_scores.values())
    overall_health = _pct(healthy_all, total_all)

    metrics = {
        "providers": provider_scores,
        "overall_health": overall_health,
        "unhealthy_providers": unhealthy_providers,
        "trends": trend_notes,
    }

    # ── 6. Audit trail activity ────────────────────────────────────────────
    provider_summary = ", ".join(
        f"{p}={s['health_score']}%" for p, s in provider_scores.items()
    )
    _insert_activity(db, organization_id,
        content=(
            f"API health check: {len(provider_scores)} providers, "
            f"overall {overall_health}% healthy. {provider_summary}"
        ),
        report_data={"agent": "api_health_checker", "metrics": metrics},
        gateway=gateway,
    )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"API health check commit failed for org {organization_id}: {e}")
        raise

    return {
        "summary": (
            f"Checked {len(provider_scores)} providers ({total_all} tokens), "
            f"overall {overall_health}% health. "
            f"Unhealthy: {', '.join(unhealthy_providers) if unhealthy_providers else 'none'}"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "metrics": metrics,
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
    gateway=None,
) -> Dict[str, Any]:
    """
    Proactive token management:
    - Find tokens expiring within 15 minutes
    - For Microsoft: attempt actual refresh via dre_helpers.refresh_microsoft_token
    - For other providers: mark as 'needs_refresh' and create reconnection task
    - Track per-provider refresh success/failure rates
    - Detect tokens stuck in 'error' state for 24+ hours and escalate
    - Log all refresh attempts as activities for audit trail
    """
    actions = 0
    notifications_sent = 0
    refreshed = 0
    failed = 0
    marked_needs_refresh = 0
    per_provider: Dict[str, Dict[str, int]] = {}

    # ── 1. Find tokens expiring within 15 minutes ─────────────────────────
    expiring = db.execute(text("""
        SELECT id, provider, user_id, refresh_token, status
        FROM oauth_tokens
        WHERE organization_id = :org_id
          AND is_active = true
          AND token_expires_at IS NOT NULL
          AND token_expires_at < CURRENT_TIMESTAMP + INTERVAL '15 minutes'
          AND token_expires_at > CURRENT_TIMESTAMP
          AND refresh_token IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    # ── 2. Attempt refresh for each expiring token ─────────────────────────
    for tok in expiring:
        tok_id = tok[0]
        provider = tok[1]
        user_id = tok[2]
        # refresh_token = tok[3]  -- used internally by provider-specific logic

        if provider not in per_provider:
            per_provider[provider] = {"refreshed": 0, "failed": 0, "needs_refresh": 0}

        if provider == "microsoft":
            try:
                # refresh_microsoft_token is async; run synchronously in agent context
                import asyncio
                from services.dre_helpers import refresh_microsoft_token

                # Fetch the ORM record for the refresh function
                from database.models.security import OAuthToken
                from database import SessionLocal

                oauth_record = db.execute(text("""
                    SELECT id FROM oauth_tokens WHERE id = :id
                """), {"id": tok_id}).fetchone()

                if oauth_record:
                    # The refresh function expects the ORM object.
                    # Load it via the current session.
                    from sqlalchemy import select
                    orm_token = db.get(OAuthToken, tok_id) if hasattr(db, 'get') else None

                    if orm_token is None:
                        # Fallback: query directly
                        orm_result = db.execute(text("""
                            SELECT id FROM oauth_tokens WHERE id = :id
                        """), {"id": tok_id}).fetchone()
                        if orm_result:
                            # Mark for manual refresh if we can't load ORM object
                            db.execute(text("""
                                UPDATE oauth_tokens
                                SET status = 'needs_refresh'
                                WHERE id = :id
                            """), {"id": tok_id})
                            marked_needs_refresh += 1
                            per_provider[provider]["needs_refresh"] += 1
                            actions += 1
                            continue

                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Already in async context; schedule coroutine
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                result = pool.submit(
                                    asyncio.run,
                                    refresh_microsoft_token(orm_token, db)
                                ).result(timeout=15)
                        else:
                            result = asyncio.run(
                                refresh_microsoft_token(orm_token, db)
                            )
                    except RuntimeError:
                        # No event loop; create one
                        result = asyncio.run(
                            refresh_microsoft_token(orm_token, db)
                        )

                    if result and result.get("success"):
                        refreshed += 1
                        per_provider[provider]["refreshed"] += 1
                        actions += 1
                        logger.info(
                            f"Refreshed Microsoft token id={tok_id} for user {user_id}"
                        )
                    else:
                        error_msg = (result or {}).get("error", "Unknown error")
                        needs_reauth = (result or {}).get("needs_reauth", False)
                        failed += 1
                        per_provider[provider]["failed"] += 1

                        if needs_reauth:
                            db.execute(text("""
                                UPDATE oauth_tokens SET status = 'expired'
                                WHERE id = :id
                            """), {"id": tok_id})
                        else:
                            db.execute(text("""
                                UPDATE oauth_tokens SET status = 'error'
                                WHERE id = :id
                            """), {"id": tok_id})

                        logger.warning(
                            f"Microsoft token refresh failed for user {user_id}: {error_msg}"
                        )
            except ImportError:
                logger.warning("Could not import refresh_microsoft_token; marking token for manual refresh")
                db.execute(text("""
                    UPDATE oauth_tokens SET status = 'needs_refresh'
                    WHERE id = :id
                """), {"id": tok_id})
                marked_needs_refresh += 1
                per_provider[provider]["needs_refresh"] += 1
                actions += 1
            except Exception as e:
                failed += 1
                per_provider.setdefault(provider, {"refreshed": 0, "failed": 0, "needs_refresh": 0})
                per_provider[provider]["failed"] += 1
                logger.warning(f"Token refresh error for Microsoft user {user_id}: {e}")
                db.execute(text("""
                    UPDATE oauth_tokens SET status = 'error'
                    WHERE id = :id
                """), {"id": tok_id})
        else:
            # Non-Microsoft providers: mark for manual reconnection
            db.execute(text("""
                UPDATE oauth_tokens SET status = 'needs_refresh'
                WHERE id = :id
            """), {"id": tok_id})
            marked_needs_refresh += 1
            per_provider.setdefault(provider, {"refreshed": 0, "failed": 0, "needs_refresh": 0})
            per_provider[provider]["needs_refresh"] += 1
            actions += 1

            # Create reconnection task (dedup 6h)
            _insert_task(
                db, organization_id,
                title=f"Reconnect {provider} integration (token expiring)",
                description=(
                    f"OAuth token for {provider} (user {user_id}) is expiring and cannot be "
                    f"auto-refreshed. Please re-authenticate from Settings > Integrations."
                ),
                priority="high",
                due_days=1,
                dedup_hours=6,
                gateway=gateway,
            )

    # ── 3. Detect stale error tokens (error state 24+ hours) ──────────────
    stale_errors = db.execute(text("""
        SELECT id, provider, user_id
        FROM oauth_tokens
        WHERE organization_id = :org_id
          AND is_active = true
          AND status = 'error'
          AND token_expires_at < CURRENT_TIMESTAMP - INTERVAL '24 hours'
    """), {"org_id": organization_id}).fetchall()

    stale_count = len(stale_errors)
    stale_providers: Dict[str, int] = {}
    for stale in stale_errors:
        provider = stale[1]
        stale_providers[provider] = stale_providers.get(provider, 0) + 1

    # Create escalation tasks for stale errors
    for provider, count in stale_providers.items():
        created = _insert_task(
            db, organization_id,
            title=f"Escalation: {provider} has {count} tokens in error 24+ hours",
            description=(
                f"{count} {provider} OAuth token(s) have been in error state for over 24 hours. "
                f"These integrations are non-functional. Investigate root cause — "
                f"possible credential rotation, API outage, or revoked access."
            ),
            priority="high",
            due_days=1,
            dedup_hours=24,
            gateway=gateway,
        )
        if created:
            actions += 1

    # ── 4. Audit trail ─────────────────────────────────────────────────────
    if expiring or stale_errors:
        provider_detail = "; ".join(
            f"{p}: refreshed={s['refreshed']}, failed={s['failed']}, needs_refresh={s['needs_refresh']}"
            for p, s in per_provider.items()
        )
        _insert_activity(db, organization_id,
            content=(
                f"Token refresh: {refreshed} refreshed, {failed} failed, "
                f"{marked_needs_refresh} marked needs_refresh, {stale_count} stale errors. "
                f"Per-provider: {provider_detail}"
            ),
            report_data={
                "agent": "token_refresh",
                "refreshed": refreshed,
                "failed": failed,
                "marked_needs_refresh": marked_needs_refresh,
                "stale_error_count": stale_count,
                "per_provider": per_provider,
                "stale_providers": stale_providers,
            },
            gateway=gateway,
        )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Token refresh commit failed for org {organization_id}: {e}")
        raise

    return {
        "summary": (
            f"Expiring: {len(expiring)}, refreshed: {refreshed}, failed: {failed}, "
            f"needs_refresh: {marked_needs_refresh}, stale errors: {stale_count}"
        ),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "metrics": {
            "expiring_found": len(expiring),
            "refreshed": refreshed,
            "failed": failed,
            "marked_needs_refresh": marked_needs_refresh,
            "stale_error_count": stale_count,
            "per_provider": per_provider,
            "stale_providers": stale_providers,
        },
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
    gateway=None,
) -> Dict[str, Any]:
    """
    Agent fleet performance analytics:
    - Per-agent: runs, success rate, avg/max duration, total actions, total notifications
    - Identify degrading agents (success rate < 80% or avg duration 2x+ baseline)
    - Identify top performers by actions-per-run ratio
    - Create health alert tasks for degrading agents with error patterns
    - Store fleet health as structured JSON activity
    - Calculate fleet-wide aggregate metrics
    """
    actions = 0
    notifications_sent = 0

    # ── 1. Current window stats (last 4 hours) ────────────────────────────
    stats = db.execute(text("""
        SELECT
            agent_name,
            COUNT(*) as runs,
            COUNT(CASE WHEN success THEN 1 END) as successes,
            COALESCE(SUM(actions_taken), 0) as total_actions,
            COALESCE(SUM(notifications_sent), 0) as total_notifs,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_s,
            MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_duration_s,
            string_agg(DISTINCT CASE WHEN NOT success THEN LEFT(error, 120) END, ' | ') as error_samples
        FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND started_at >= CURRENT_TIMESTAMP - INTERVAL '4 hours'
        GROUP BY agent_name
        ORDER BY runs DESC
    """), {"org_id": organization_id}).fetchall()

    if not stats:
        return {
            "summary": "No agent runs in last 4 hours",
            "actions_taken": 0,
            "notifications_sent": 0,
            "metrics": {"agents": {}, "fleet_total_runs": 0},
        }

    # ── 2. Load previous window stats for trend comparison ─────────────────
    prev_stats = db.execute(text("""
        SELECT
            agent_name,
            COUNT(*) as runs,
            COUNT(CASE WHEN success THEN 1 END) as successes,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_s
        FROM autonomous_agent_runs
        WHERE organization_id = :org_id
          AND started_at >= CURRENT_TIMESTAMP - INTERVAL '8 hours'
          AND started_at < CURRENT_TIMESTAMP - INTERVAL '4 hours'
        GROUP BY agent_name
    """), {"org_id": organization_id}).fetchall()

    prev_by_name: Dict[str, Dict[str, float]] = {}
    for ps in prev_stats:
        prev_by_name[ps[0]] = {
            "runs": _safe_int(ps[1]),
            "successes": _safe_int(ps[2]),
            "avg_duration_s": _safe_float(ps[3]),
        }

    # ── 3. Analyze each agent ──────────────────────────────────────────────
    agent_details: Dict[str, Dict[str, Any]] = {}
    degrading_agents: List[Dict[str, Any]] = []
    top_performers: List[Tuple[str, float]] = []

    fleet_total_runs = 0
    fleet_total_successes = 0
    fleet_total_actions = 0
    fleet_total_notifs = 0

    for s in stats:
        agent_name = s[0]
        runs = _safe_int(s[1])
        successes = _safe_int(s[2])
        total_actions_agent = _safe_int(s[3])
        total_notifs_agent = _safe_int(s[4])
        avg_dur = _safe_float(s[5])
        max_dur = _safe_float(s[6])
        error_samples = s[7] or ""

        success_rate = _pct(successes, runs)
        actions_per_run = _safe_div(total_actions_agent, runs)

        fleet_total_runs += runs
        fleet_total_successes += successes
        fleet_total_actions += total_actions_agent
        fleet_total_notifs += total_notifs_agent

        detail: Dict[str, Any] = {
            "runs": runs,
            "successes": successes,
            "success_rate": success_rate,
            "total_actions": total_actions_agent,
            "total_notifications": total_notifs_agent,
            "avg_duration_s": round(avg_dur, 2),
            "max_duration_s": round(max_dur, 2),
            "actions_per_run": round(actions_per_run, 2),
        }

        # ── Trend detection ───────────────────────────────────────────────
        is_degrading = False
        degradation_reasons: List[str] = []

        prev = prev_by_name.get(agent_name)
        if prev:
            prev_success_rate = _pct(prev["successes"], prev["runs"])
            prev_avg_dur = prev["avg_duration_s"]
            detail["prev_success_rate"] = prev_success_rate
            detail["prev_avg_duration_s"] = round(prev_avg_dur, 2)

            # Success rate dropped below 80%
            if success_rate < 80.0:
                is_degrading = True
                degradation_reasons.append(f"success rate {success_rate}% (was {prev_success_rate}%)")

            # Avg duration increased 2x+
            if prev_avg_dur > 0 and avg_dur > prev_avg_dur * 2:
                is_degrading = True
                degradation_reasons.append(
                    f"avg duration {avg_dur:.1f}s (was {prev_avg_dur:.1f}s, {avg_dur/prev_avg_dur:.1f}x increase)"
                )
        else:
            # No previous data; still flag if success rate below threshold
            if success_rate < 80.0 and runs >= 2:
                is_degrading = True
                degradation_reasons.append(f"success rate {success_rate}% (no prior baseline)")

        if is_degrading:
            detail["degrading"] = True
            detail["degradation_reasons"] = degradation_reasons
            degrading_agents.append({
                "agent_name": agent_name,
                "reasons": degradation_reasons,
                "error_samples": error_samples[:500],
            })

        # Top performers: highest actions_per_run (minimum 2 runs)
        if runs >= 2 and success_rate >= 80.0:
            top_performers.append((agent_name, actions_per_run))

        agent_details[agent_name] = detail

    # Sort top performers
    top_performers.sort(key=lambda x: x[1], reverse=True)
    top_5 = top_performers[:5]

    # ── 4. Create alert tasks for degrading agents ─────────────────────────
    for deg in degrading_agents:
        reasons_str = "; ".join(deg["reasons"])
        error_snippet = deg["error_samples"][:300] if deg["error_samples"] else "No error details captured"

        created = _insert_task(
            db, organization_id,
            title=f"Agent health alert: {deg['agent_name']} degrading",
            description=(
                f"Agent '{deg['agent_name']}' is degrading in the last 4-hour window. "
                f"Issues: {reasons_str}. "
                f"Recent errors: {error_snippet}. "
                f"Investigate logs and consider disabling if consistently failing."
            ),
            priority="high",
            due_days=1,
            dedup_hours=8,
            gateway=gateway,
        )
        if created:
            actions += 1

    # ── 5. Fleet-wide summary ──────────────────────────────────────────────
    fleet_success_rate = _pct(fleet_total_successes, fleet_total_runs)

    metrics = {
        "agents": agent_details,
        "fleet_total_runs": fleet_total_runs,
        "fleet_total_successes": fleet_total_successes,
        "fleet_success_rate": fleet_success_rate,
        "fleet_total_actions": fleet_total_actions,
        "fleet_total_notifications": fleet_total_notifs,
        "degrading_agents": [d["agent_name"] for d in degrading_agents],
        "top_performers": [{"agent": name, "actions_per_run": round(apr, 2)} for name, apr in top_5],
    }

    # ── 6. Audit trail activity ────────────────────────────────────────────
    top_str = ", ".join(f"{name}({apr:.1f}/run)" for name, apr in top_5[:3])
    deg_str = ", ".join(d["agent_name"] for d in degrading_agents[:5])

    _insert_activity(db, organization_id,
        content=(
            f"Fleet analytics: {fleet_total_runs} runs across {len(agent_details)} agents, "
            f"{fleet_success_rate}% success, {fleet_total_actions} actions. "
            f"Degrading: {deg_str or 'none'}. Top: {top_str or 'n/a'}."
        ),
        report_data={"agent": "log_aggregation", "metrics": metrics},
        gateway=gateway,
    )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Log aggregation commit failed for org {organization_id}: {e}")
        raise

    summary_lines = [
        f"Fleet: {fleet_total_runs} runs, {fleet_success_rate}% success, "
        f"{fleet_total_actions} actions across {len(agent_details)} agents"
    ]
    if degrading_agents:
        summary_lines.append(f"Degrading: {deg_str}")
    if top_5:
        summary_lines.append(f"Top performers: {top_str}")

    return {
        "summary": ". ".join(summary_lines),
        "actions_taken": actions,
        "notifications_sent": notifications_sent,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 5. Cost Optimization Agent
# ---------------------------------------------------------------------------

# Sonnet pricing (as of 2026)
_INPUT_COST_PER_MTOK = 3.0   # $3 per million input tokens
_OUTPUT_COST_PER_MTOK = 15.0  # $15 per million output tokens

# Configurable daily cost alert threshold (env var or default $10)
_COST_ALERT_THRESHOLD = float(os.environ.get("AI_DAILY_COST_ALERT", "10.0"))


@autonomous_agent(
    name="cost_optimization",
    description="Track AI token usage and identify cost optimization opportunities",
    frequency=AgentFrequency.DAILY_6PM,
    max_runtime_seconds=60,
)
def cost_optimization(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    AI spend tracking and optimization:
    - Query agent_invocations for today's usage (graceful if table missing)
    - Calculate cost: input tokens at $3/MTok, output at $15/MTok
    - Break down by tool_name to find most expensive operations
    - Calculate cost per active user
    - Compare to 7-day rolling average to detect spikes
    - Identify tools with high token usage but low success rate
    - Create alert if daily cost exceeds threshold (env: AI_DAILY_COST_ALERT)
    - Store detailed cost breakdown as structured activity
    """
    actions = 0
    notifications_sent = 0

    # ── 1. Query today's AI invocation data ────────────────────────────────
    try:
        # Verify table exists first (agent_invocations may not be deployed)
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'agent_invocations'
            )
        """)).scalar()

        if not table_check:
            _insert_activity(db, organization_id,
                content="Cost optimization: agent_invocations table not yet deployed. Skipping.",
                report_data={"agent": "cost_optimization", "status": "table_missing"},
                gateway=gateway,
            )
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Cost optimization commit failed: {e}")
            return {
                "summary": "Agent invocation tracking table not available",
                "actions_taken": 0,
                "notifications_sent": 0,
                "metrics": {"status": "table_missing"},
            }

        # ── 2. Today's aggregate usage ─────────────────────────────────────
        today_totals = db.execute(text("""
            SELECT
                COUNT(*) as total_invocations,
                COALESCE(SUM(tokens_input), 0) as total_input_tokens,
                COALESCE(SUM(tokens_output), 0) as total_output_tokens,
                COALESCE(AVG(tokens_input + tokens_output), 0) as avg_tokens_per_req,
                COALESCE(MAX(tokens_input + tokens_output), 0) as max_tokens_per_req,
                COALESCE(AVG(duration_ms), 0) as avg_duration_ms,
                COUNT(CASE WHEN status = 'success' THEN 1 END) as success_count,
                COUNT(CASE WHEN status != 'success' THEN 1 END) as failure_count
            FROM agent_invocations
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
        """), {"org_id": organization_id}).fetchone()

        total_invocations = _safe_int(today_totals[0])
        total_input = _safe_int(today_totals[1])
        total_output = _safe_int(today_totals[2])
        avg_tokens = _safe_float(today_totals[3])
        max_tokens = _safe_int(today_totals[4])
        avg_duration = _safe_float(today_totals[5])
        success_count = _safe_int(today_totals[6])
        failure_count = _safe_int(today_totals[7])

        if total_invocations == 0:
            _insert_activity(db, organization_id,
                content="Cost optimization: No AI invocations today.",
                report_data={"agent": "cost_optimization", "status": "no_invocations"},
                gateway=gateway,
            )
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Cost optimization commit failed: {e}")
            return {
                "summary": "No AI invocations tracked today",
                "actions_taken": 0,
                "notifications_sent": 0,
                "metrics": {"status": "no_invocations", "total_invocations": 0},
            }

        # ── 3. Calculate costs ─────────────────────────────────────────────
        input_cost = (total_input / 1_000_000) * _INPUT_COST_PER_MTOK
        output_cost = (total_output / 1_000_000) * _OUTPUT_COST_PER_MTOK
        total_cost = input_cost + output_cost

        # ── 4. Per-tool breakdown ──────────────────────────────────────────
        tool_breakdown_rows = db.execute(text("""
            SELECT
                tool_name,
                COUNT(*) as invocations,
                COALESCE(SUM(tokens_input), 0) as input_tokens,
                COALESCE(SUM(tokens_output), 0) as output_tokens,
                COALESCE(AVG(duration_ms), 0) as avg_duration_ms,
                COUNT(CASE WHEN status = 'success' THEN 1 END) as successes,
                COUNT(CASE WHEN status != 'success' THEN 1 END) as failures
            FROM agent_invocations
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
            GROUP BY tool_name
            ORDER BY (COALESCE(SUM(tokens_input), 0) + COALESCE(SUM(tokens_output), 0)) DESC
            LIMIT 25
        """), {"org_id": organization_id}).fetchall()

        per_tool: List[Dict[str, Any]] = []
        optimization_candidates: List[Dict[str, Any]] = []

        for row in tool_breakdown_rows:
            tool_name = row[0] or "unknown"
            inv = _safe_int(row[1])
            inp = _safe_int(row[2])
            out = _safe_int(row[3])
            dur = _safe_float(row[4])
            succ = _safe_int(row[5])
            fail = _safe_int(row[6])

            tool_input_cost = (inp / 1_000_000) * _INPUT_COST_PER_MTOK
            tool_output_cost = (out / 1_000_000) * _OUTPUT_COST_PER_MTOK
            tool_cost = tool_input_cost + tool_output_cost
            tool_success_rate = _pct(succ, inv)

            tool_entry = {
                "tool_name": tool_name,
                "invocations": inv,
                "input_tokens": inp,
                "output_tokens": out,
                "cost": round(tool_cost, 4),
                "success_rate": tool_success_rate,
                "avg_duration_ms": round(dur, 1),
            }
            per_tool.append(tool_entry)

            # Flag tools with high spend but low success rate as optimization targets
            if tool_cost > 0.10 and tool_success_rate < 70.0:
                optimization_candidates.append({
                    "tool_name": tool_name,
                    "cost": round(tool_cost, 4),
                    "success_rate": tool_success_rate,
                    "suggestion": (
                        f"Tool '{tool_name}' spent ${tool_cost:.2f} today with only "
                        f"{tool_success_rate}% success rate. Consider prompt optimization, "
                        f"caching, or reducing retry attempts."
                    ),
                })

        # ── 5. Cost per active user ────────────────────────────────────────
        active_users_count = db.execute(text("""
            SELECT COUNT(DISTINCT user_id) FROM agent_invocations
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
        """), {"org_id": organization_id}).scalar() or 1

        cost_per_user = _safe_div(total_cost, active_users_count)

        # ── 6. 7-day rolling average comparison ───────────────────────────
        rolling_avg = db.execute(text("""
            SELECT
                COALESCE(AVG(daily_cost), 0) as avg_daily_cost,
                COALESCE(MAX(daily_cost), 0) as max_daily_cost
            FROM (
                SELECT
                    DATE(created_at) as day,
                    (SUM(tokens_input) / 1000000.0 * :input_rate +
                     SUM(tokens_output) / 1000000.0 * :output_rate) as daily_cost
                FROM agent_invocations
                WHERE organization_id = :org_id
                  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
                  AND created_at < CURRENT_DATE
                GROUP BY DATE(created_at)
            ) daily_costs
        """), {
            "org_id": organization_id,
            "input_rate": _INPUT_COST_PER_MTOK,
            "output_rate": _OUTPUT_COST_PER_MTOK,
        }).fetchone()

        avg_daily_cost = _safe_float(rolling_avg[0]) if rolling_avg else 0.0
        max_daily_cost = _safe_float(rolling_avg[1]) if rolling_avg else 0.0

        cost_vs_average = "N/A"
        spike_detected = False
        if avg_daily_cost > 0:
            ratio = total_cost / avg_daily_cost
            cost_vs_average = f"{ratio:.1f}x"
            if ratio > 2.0:
                spike_detected = True

        # ── 7. Build optimization suggestions ──────────────────────────────
        suggestions: List[str] = []

        if spike_detected:
            suggestions.append(
                f"Cost spike: today's ${total_cost:.2f} is {cost_vs_average} the 7-day average (${avg_daily_cost:.2f})."
            )

        if optimization_candidates:
            for cand in optimization_candidates[:3]:
                suggestions.append(cand["suggestion"])

        if failure_count > 0 and _pct(failure_count, total_invocations) > 20:
            suggestions.append(
                f"High failure rate: {failure_count}/{total_invocations} invocations failed. "
                f"Failed calls still consume tokens. Investigate error patterns."
            )

        # ── 8. Alert if cost exceeds threshold ────────────────────────────
        if total_cost > _COST_ALERT_THRESHOLD:
            created = _insert_task(
                db, organization_id,
                title=f"AI cost alert: ${total_cost:.2f} today (threshold: ${_COST_ALERT_THRESHOLD:.2f})",
                description=(
                    f"AI token spend estimated at ${total_cost:.2f} today "
                    f"({total_input:,} input + {total_output:,} output tokens "
                    f"across {total_invocations} invocations). "
                    f"7-day avg: ${avg_daily_cost:.2f}. "
                    f"Top cost driver: {per_tool[0]['tool_name'] if per_tool else 'N/A'} "
                    f"(${per_tool[0]['cost']:.2f}). "
                    f"Review tool usage and consider optimization."
                ),
                priority="medium",
                due_days=1,
                dedup_hours=24,
                gateway=gateway,
            )
            if created:
                actions += 1

        if spike_detected:
            created = _insert_task(
                db, organization_id,
                title=f"AI cost spike: {cost_vs_average} above 7-day average",
                description=(
                    f"Today's AI spend (${total_cost:.2f}) is {cost_vs_average} "
                    f"the 7-day rolling average (${avg_daily_cost:.2f}). "
                    f"Max in last 7 days: ${max_daily_cost:.2f}. "
                    f"Investigate whether this is expected growth or anomalous usage."
                ),
                priority="medium",
                due_days=2,
                dedup_hours=24,
                gateway=gateway,
            )
            if created:
                actions += 1

        # ── 9. Store detailed breakdown as activity ────────────────────────
        metrics: Dict[str, Any] = {
            "total_cost": round(total_cost, 4),
            "input_cost": round(input_cost, 4),
            "output_cost": round(output_cost, 4),
            "total_invocations": total_invocations,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "avg_tokens_per_request": round(avg_tokens, 1),
            "max_tokens_per_request": max_tokens,
            "avg_duration_ms": round(avg_duration, 1),
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": _pct(success_count, total_invocations),
            "active_users": active_users_count,
            "cost_per_user": round(cost_per_user, 4),
            "rolling_7d_avg_cost": round(avg_daily_cost, 4),
            "rolling_7d_max_cost": round(max_daily_cost, 4),
            "cost_vs_average": cost_vs_average,
            "spike_detected": spike_detected,
            "per_tool": per_tool[:15],  # Top 15 for storage
            "optimization_candidates": optimization_candidates[:5],
            "suggestions": suggestions,
        }

        top_tool_str = ", ".join(
            f"{t['tool_name']}(${t['cost']:.2f})" for t in per_tool[:3]
        )

        _insert_activity(db, organization_id,
            content=(
                f"AI cost report: ${total_cost:.2f} today ({total_invocations} invocations, "
                f"{total_input + total_output:,} tokens). "
                f"7d avg: ${avg_daily_cost:.2f}. "
                f"Top tools: {top_tool_str}. "
                f"Cost/user: ${cost_per_user:.3f}. "
                f"{'SPIKE DETECTED. ' if spike_detected else ''}"
                f"{len(suggestions)} optimization suggestions."
            ),
            report_data={"agent": "cost_optimization", "metrics": metrics},
            gateway=gateway,
        )

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Cost optimization commit failed for org {organization_id}: {e}")
            raise

        return {
            "summary": (
                f"${total_cost:.2f} today ({total_invocations} invocations, "
                f"{total_input + total_output:,} tokens). "
                f"7d avg: ${avg_daily_cost:.2f}, {cost_vs_average} ratio. "
                f"{'SPIKE. ' if spike_detected else ''}"
                f"{len(optimization_candidates)} optimization targets"
            ),
            "actions_taken": actions,
            "notifications_sent": notifications_sent,
            "metrics": metrics,
        }

    except Exception as e:
        # Graceful fallback if agent_invocations table doesn't exist or query fails
        logger.warning(f"Cost optimization query failed for org {organization_id}: {e}")

        try:
            db.rollback()
        except Exception:
            pass

        return {
            "summary": f"Agent invocation tracking unavailable: {type(e).__name__}",
            "actions_taken": 0,
            "notifications_sent": 0,
            "metrics": {"status": "error", "error": str(e)[:500]},
        }
