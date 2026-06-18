"""
Scheduled Jobs Registry — Central catalog of ALL background jobs.

Every periodic job in the system is registered here. The SchedulerService
reads this registry at startup and registers each job with APScheduler.

Each entry specifies:
  - name:     Unique job ID (used for APScheduler id and distributed lock key)
  - func:     Callable (sync) to execute
  - trigger:  APScheduler trigger type ("cron" or "interval")
  - kwargs:   Trigger-specific kwargs (minute, hour, minutes, hours, etc.)
  - domain:   Logical grouping for display (sync, cleanup, monitoring, notification, workflow, compliance, ai)
  - description: Human-readable description
  - lock_ttl: Max seconds the distributed lock is held (auto-expire safety)

Jobs are grouped by domain:
  1. NOTIFICATION JOBS   — application reminders, appointment reminders, doc expiration
  2. WORKFLOW JOBS       — task generation, status processing, escalation, completion, AI execution
  3. CLEANUP JOBS        — stale applications, slot holds, audit log retention
  4. SYNC JOBS           — calendar sync, email inbox sync, MS365, Salesforce
  5. MONITORING JOBS     — webhook retry, SLA tracking, ops manager
  6. COMPLIANCE JOBS     — SOC 2 scans, retention enforcement, data classification
  7. AI JOBS             — prospect re-engagement, no-show recovery, listing agent updates
  8. AGENT JOBS          — agent message processor, autonomous agents (registered dynamically)
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class JobDefinition:
    """Definition of a scheduled job."""
    name: str
    func: Callable
    trigger: str  # "cron" or "interval"
    trigger_kwargs: Dict[str, Any]
    domain: str
    description: str
    lock_ttl: int = 300  # seconds — max lock hold time


# ============================================================================
# JOB REGISTRY — populated lazily to avoid import-time side effects
# ============================================================================

_registry: List[JobDefinition] = []
_registry_populated = False


def _populate_registry():
    """Populate the job registry with all scheduled jobs.

    Uses lazy imports throughout to avoid circular import issues —
    the same pattern used by the existing scheduler_service.py job methods.
    """
    global _registry, _registry_populated
    if _registry_populated:
        return
    _registry_populated = True

    # Import the existing SchedulerService singleton — its methods ARE the
    # job implementations for notification, workflow, cleanup, and AI jobs.
    from services.scheduler_service import scheduler_service as _svc

    jobs: List[JobDefinition] = []

    # ====================================================================
    # 1. NOTIFICATION JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="application_reminders",
        func=_svc.send_application_reminders,
        trigger="cron",
        trigger_kwargs={"minute": 7},
        domain="notification",
        description="Send reminders for incomplete applications",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="document_expiration_check",
        func=_svc.check_document_expirations,
        trigger="cron",
        trigger_kwargs={"hour": 9, "minute": 15},
        domain="notification",
        description="Check for expiring documents and notify",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="appointment_reminders",
        func=_svc.send_appointment_reminders,
        trigger="cron",
        trigger_kwargs={"minute": "5,20,35,50"},
        domain="notification",
        description="Send reminders for upcoming appointments (24h, 1h)",
        lock_ttl=180,
    ))

    # ====================================================================
    # 2. WORKFLOW JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="workflow_task_generation",
        func=_svc.run_workflow_task_generation,
        trigger="cron",
        trigger_kwargs={"minute": "9,24,39,54"},
        domain="workflow",
        description="Generate tasks for active workflows",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="workflow_status_processing",
        func=_svc.run_workflow_status_processing,
        trigger="cron",
        trigger_kwargs={"minute": "3,13,23,33,43,53"},
        domain="workflow",
        description="Process workflow status changes and auto-enroll",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="workflow_escalation",
        func=_svc.run_workflow_escalation,
        trigger="cron",
        trigger_kwargs={"minute": 37},
        domain="workflow",
        description="Escalate overdue workflow tasks",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="workflow_completion_check",
        func=_svc.run_workflow_completion_check,
        trigger="cron",
        trigger_kwargs={"minute": "12,42"},
        domain="workflow",
        description="Check for workflows that should be completed",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="ai_autonomous_execution",
        func=_svc.run_ai_autonomous_execution,
        trigger="cron",
        trigger_kwargs={"minute": "1,16,31,46"},
        domain="workflow",
        description="Run AI autonomous task execution for high-confidence tasks",
        lock_ttl=180,
    ))

    # ====================================================================
    # 3. CLEANUP JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="stale_cleanup",
        func=_svc.cleanup_stale_applications,
        trigger="cron",
        trigger_kwargs={"hour": 0, "minute": 30},
        domain="cleanup",
        description="Archive applications inactive for 90+ days",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="slot_hold_cleanup",
        func=_svc.cleanup_slot_holds,
        trigger="interval",
        trigger_kwargs={"minutes": 5},
        domain="cleanup",
        description="Expire stale slot holds and delete old records",
        lock_ttl=30,
    ))

    jobs.append(JobDefinition(
        name="audit_log_retention",
        func=_svc.cleanup_audit_logs,
        trigger="cron",
        trigger_kwargs={"hour": 3, "minute": 17},
        domain="cleanup",
        description="Purge audit log entries older than retention period",
        lock_ttl=300,
    ))


    jobs.append(JobDefinition(
        name="calendar_feed_cleanup",
        func=_svc.cleanup_expired_calendar_feeds,
        trigger="cron",
        trigger_kwargs={"hour": 2, "minute": 45},
        domain="cleanup",
        description="Delete expired calendar feed tokens (expires_at < NOW())",
        lock_ttl=60,
    ))

    # ====================================================================
    # 4. SYNC JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="outbound_calendar_sync",
        func=_svc.run_outbound_calendar_sync,
        trigger="cron",
        trigger_kwargs={"minute": "3,13,23,33,43,53"},
        domain="sync",
        description="Retry failed/pending outbound calendar syncs",
        lock_ttl=120,
    ))

    # Calendar sync push/pull jobs (Salesforce ↔ CRM, every 2 minutes)
    try:
        from tasks.calendar_sync_tasks import (
            process_pending_sync_events_sync,
            poll_salesforce_events_sync,
            check_sync_health_sync,
        )
        jobs.append(JobDefinition(
            name="calendar_sync_pending",
            func=process_pending_sync_events_sync,
            trigger="interval",
            trigger_kwargs={"minutes": 2},
            domain="sync",
            description="Process pending calendar sync events (push CRM → Salesforce)",
            lock_ttl=110,
        ))
        jobs.append(JobDefinition(
            name="calendar_sync_poll",
            func=poll_salesforce_events_sync,
            trigger="interval",
            trigger_kwargs={"minutes": 2},
            domain="sync",
            description="Poll Salesforce for event changes (pull Salesforce → CRM)",
            lock_ttl=110,
        ))
        jobs.append(JobDefinition(
            name="calendar_sync_health",
            func=check_sync_health_sync,
            trigger="interval",
            trigger_kwargs={"minutes": 15},
            domain="sync",
            description="Calendar sync health check",
            lock_ttl=60,
        ))
    except ImportError as e:
        logger.warning("Calendar sync tasks not available: %s", e)

    # MS365 and email sync jobs are registered dynamically from app_lifespan.py
    # via scheduler_service.register_job() because they need async wrappers
    # defined at startup time. They still get distributed lock wrapping.

    # ====================================================================
    # 5. MONITORING JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="webhook_dead_letter_retry",
        func=_svc.retry_dead_letter_webhooks,
        trigger="cron",
        trigger_kwargs={"minute": 22, "hour": "1,3,5,7,9,11,13,15,17,19,21,23"},
        domain="monitoring",
        description="Auto-retry dead-lettered webhook deliveries",
        lock_ttl=180,
    ))

    # ====================================================================
    # 6. AI JOBS
    # ====================================================================

    jobs.append(JobDefinition(
        name="prospect_reengagement_scan",
        func=_svc.run_prospect_reengagement_scan,
        trigger="cron",
        trigger_kwargs={"hour": 9, "minute": 45},
        domain="ai",
        description="Scan for stale prospects and initiate AI re-engagement",
        lock_ttl=300,
    ))

    jobs.append(JobDefinition(
        name="prospect_reengagement_expiry",
        func=_svc.run_prospect_reengagement_expiry,
        trigger="cron",
        trigger_kwargs={"hour": 10, "minute": 15},
        domain="ai",
        description="Expire stale AI re-engagement conversations",
        lock_ttl=120,
    ))

    jobs.append(JobDefinition(
        name="no_show_recovery",
        func=_svc.run_no_show_recovery,
        trigger="cron",
        trigger_kwargs={"minute": "8,23,38,53"},
        domain="ai",
        description="No-show detection and recovery step execution",
        lock_ttl=180,
    ))

    jobs.append(JobDefinition(
        name="listing_weekly_updates",
        func=_svc.run_listing_weekly_updates,
        trigger="cron",
        trigger_kwargs={"day_of_week": "mon", "hour": 9, "minute": 25},
        domain="ai",
        description="Send listing agent weekly updates",
        lock_ttl=300,
    ))

    # ====================================================================
    # 8. AGENT JOBS
    # ====================================================================

    # Agent message processor — processes pending AI agent messages
    try:
        from services.agent_message_processor import process_pending_messages
        jobs.append(JobDefinition(
            name="agent_message_processor",
            func=process_pending_messages,
            trigger="interval",
            trigger_kwargs={"minutes": 5},
            domain="agent",
            description="Process pending AI agent messages",
            lock_ttl=120,
        ))
    except ImportError as e:
        logger.warning("Agent message processor not available: %s", e)

    # Autonomous agents are registered dynamically from app_lifespan.py
    # via scheduler_service.register_job() because they depend on the
    # @autonomous_agent decorator registry which is populated at import time.

    _registry.extend(jobs)
    logger.info("Job registry populated: %d jobs", len(jobs))


def get_all_jobs() -> List[JobDefinition]:
    """Return all registered job definitions."""
    _populate_registry()
    return list(_registry)


def get_jobs_by_domain(domain: str) -> List[JobDefinition]:
    """Return jobs filtered by domain."""
    _populate_registry()
    return [j for j in _registry if j.domain == domain]


def register_external_job(job_def: JobDefinition):
    """Register a job from an external module (e.g., SOC 2, Salesforce sync).

    Called by modules that register their own jobs at startup time, allowing
    them to participate in the centralized scheduler with distributed locking.
    """
    _populate_registry()
    # Avoid duplicates
    existing_names = {j.name for j in _registry}
    if job_def.name in existing_names:
        logger.debug("Job %s already registered, skipping duplicate", job_def.name)
        return
    _registry.append(job_def)
    logger.info("External job registered: %s (%s)", job_def.name, job_def.domain)
