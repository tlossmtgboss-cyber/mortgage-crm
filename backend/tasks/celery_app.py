"""
Celery Application Configuration

Centralizes Celery configuration for background task processing.
This replaces APScheduler for distributed task execution.

Usage:
    # Start worker
    celery -A tasks.celery_app worker -l info

    # Start beat scheduler (for periodic tasks)
    celery -A tasks.celery_app beat -l info

    # Or start both together
    celery -A tasks.celery_app worker -B -l info
"""

import os
import logging
from typing import Optional
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)


def get_redis_url() -> str:
    """
    Get Redis URL from environment.

    In production, this MUST be set to a production Redis instance.
    The application will fail to start if REDIS_URL is not properly configured.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    environment = os.getenv("ENVIRONMENT", "development").lower()

    if environment in ("production", "prod"):
        if not redis_url or "localhost" in redis_url:
            raise ValueError(
                "REDIS_URL must be set to a production Redis instance in production environment. "
                "Local Redis is not acceptable for production workloads."
            )

    return redis_url


def create_celery_app(app_name: str = "perennia") -> Celery:
    """
    Create and configure Celery application.

    Args:
        app_name: Name for the Celery application

    Returns:
        Configured Celery instance
    """
    redis_url = get_redis_url()

    celery_app = Celery(
        app_name,
        broker=redis_url,
        backend=redis_url,
        include=[
            "tasks.sla_tasks",
            "tasks.agent_tasks",
            "tasks.outreach_tasks",
            "tasks.usage_aggregation_tasks",
            "tasks.calendar_sync_tasks",
            "tasks.salesforce_sync_tasks",
            "tasks.call_intelligence_tasks",
            "tasks.video_render_tasks",
            "tasks.report_tasks",
            "tasks.reminder_tasks",
            "tasks.app_completion_tasks",
        ],
    )

    # Celery configuration
    celery_app.conf.update(
        # Serialization
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,

        # Task execution
        task_acks_late=True,  # Acknowledge tasks after completion (safer)
        task_reject_on_worker_lost=True,  # Re-queue if worker dies
        task_time_limit=600,  # 10 minute hard limit
        task_soft_time_limit=540,  # 9 minute soft limit (raises exception)

        # Concurrency
        worker_concurrency=4,  # Number of worker processes
        worker_prefetch_multiplier=2,  # Tasks per worker to prefetch

        # Result backend
        result_expires=3600,  # Results expire after 1 hour

        # Retry configuration
        task_default_retry_delay=60,  # 1 minute delay between retries
        task_max_retries=3,

        # Broker connection settings
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=10,
        broker_pool_limit=10,

        # Task routing
        task_queues=(
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("high_priority", Exchange("high_priority"), routing_key="high_priority"),
            Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
            Queue("ai_tasks", Exchange("ai_tasks"), routing_key="ai_tasks"),
            Queue("video_render", Exchange("video_render"), routing_key="video_render"),
        ),
        task_default_queue="default",
        task_default_exchange="default",
        task_default_routing_key="default",

        # Task routing rules
        task_routes={
            "tasks.agent_tasks.*": {"queue": "ai_tasks"},
            "tasks.usage_aggregation_tasks.*": {"queue": "low_priority"},
            "tasks.sla_tasks.create_risk_alerts_task": {"queue": "high_priority"},
            "tasks.call_intelligence_tasks.process_transcript_task": {"queue": "ai_tasks"},
            "tasks.call_intelligence_tasks.process_batch_task": {"queue": "ai_tasks"},
            "tasks.call_intelligence_tasks.cleanup_old_results_task": {"queue": "low_priority"},
            "tasks.call_intelligence_tasks.reprocess_failed_task": {"queue": "low_priority"},
            "tasks.video_render_tasks.process_render_job": {"queue": "video_render"},
            "tasks.video_render_tasks.queue_pending_jobs": {"queue": "video_render"},
            "tasks.app_completion_tasks.trigger_application_review_task": {"queue": "default"},
            "tasks.app_completion_tasks.process_borrower_sms_response_task": {"queue": "default"},
            "tasks.app_completion_tasks.recalculate_stale_reviews_task": {"queue": "low_priority"},
            "tasks.app_completion_tasks.send_pending_reminders_task": {"queue": "default"},
        },
    )

    return celery_app


# Create the Celery app instance
celery_app = create_celery_app()


# ============================================================================
# Periodic Tasks (Beat Schedule)
# ============================================================================

celery_app.conf.beat_schedule = {
    # SLA Tasks
    "update-milestone-statuses": {
        "task": "tasks.sla_tasks.update_milestone_statuses_task",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {"queue": "default"},
    },
    "create-risk-alerts": {
        "task": "tasks.sla_tasks.create_risk_alerts_task",
        "schedule": crontab(minute="0"),  # Every hour
        "options": {"queue": "high_priority"},
    },
    "create-performance-snapshots-morning": {
        "task": "tasks.sla_tasks.create_performance_snapshot_task",
        "schedule": crontab(hour="8", minute="0"),  # 8 AM daily
        "options": {"queue": "default"},
    },
    "create-performance-snapshots-noon": {
        "task": "tasks.sla_tasks.create_performance_snapshot_task",
        "schedule": crontab(hour="12", minute="0"),  # 12 PM daily
        "options": {"queue": "default"},
    },
    "reactivate-snoozed-alerts": {
        "task": "tasks.sla_tasks.reactivate_snoozed_alerts_task",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": "default"},
    },
    "create-weekly-efficiency-reports": {
        "task": "tasks.sla_tasks.create_efficiency_reports_task",
        "schedule": crontab(hour="7", minute="0", day_of_week="monday"),  # Monday 7 AM
        "options": {"queue": "low_priority"},
    },

    # Usage Aggregation
    "run-daily-usage-aggregation": {
        "task": "tasks.usage_aggregation_tasks.run_daily_aggregation",
        "schedule": crontab(hour="1", minute="0"),  # 1 AM daily
        "options": {"queue": "low_priority"},
    },

    # Calendar Sync
    "process-pending-sync-events": {
        "task": "tasks.calendar_sync_tasks.process_pending_sync_events",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {"queue": "default"},
    },
    "poll-salesforce-events": {
        "task": "tasks.calendar_sync_tasks.poll_salesforce_events",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
        "options": {"queue": "default"},
    },
    "reconcile-calendars": {
        "task": "tasks.calendar_sync_tasks.reconcile_calendar",
        "schedule": crontab(hour="3", minute="0"),  # 3 AM daily
        "options": {"queue": "low_priority"},
    },

    # Salesforce Sync
    "sync-all-users-salesforce": {
        "task": "tasks.salesforce_sync_tasks.sync_all_users_salesforce",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {"queue": "default"},
    },
    "check-salesforce-sync-health": {
        "task": "tasks.salesforce_sync_tasks.check_salesforce_sync_health",
        "schedule": crontab(hour="*/4"),  # Every 4 hours
        "options": {"queue": "default"},
    },

    # Call Intelligence Tasks
    "cleanup-old-call-intelligence-results": {
        "task": "tasks.call_intelligence_tasks.cleanup_old_results_task",
        "schedule": crontab(hour="2", minute="30"),  # 2:30 AM daily
        "options": {"queue": "low_priority"},
        "kwargs": {"days": 90},
    },
    "reprocess-failed-extractions": {
        "task": "tasks.call_intelligence_tasks.reprocess_failed_task",
        "schedule": crontab(hour="4", minute="0"),  # 4 AM daily
        "options": {"queue": "low_priority"},
        "kwargs": {"hours": 24, "limit": 50},
    },

    # Video Render Tasks
    "queue-pending-video-render-jobs": {
        "task": "tasks.video_render_tasks.queue_pending_jobs",
        "schedule": crontab(minute="*/2"),  # Every 2 minutes
        "options": {"queue": "video_render"},
    },

    # Scheduled Report Delivery (Enterprise Readiness Domain 9, Check 9.11)
    "deliver-scheduled-reports": {
        "task": "tasks.report_tasks.deliver_scheduled_reports",
        "schedule": crontab(minute="0"),  # Every hour (checks hour_utc match)
        "options": {"queue": "low_priority"},
    },

    # Data Retention & DR Tasks
    "run-data-retention-cleanup": {
        "task": "tasks.sla_tasks.run_retention_cleanup_task",
        "schedule": crontab(hour="3", minute="30", day_of_week="sunday"),  # Sunday 3:30 AM
        "options": {"queue": "low_priority"},
        "kwargs": {"dry_run": False},
    },
    "verify-backup-integrity": {
        "task": "tasks.sla_tasks.verify_backup_task",
        "schedule": crontab(hour="5", minute="0"),  # Daily 5 AM
        "options": {"queue": "low_priority"},
    },

    # Appointment Reminders
    "process-pending-reminders": {
        "task": "tasks.reminder_tasks.process_pending_reminders",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {"queue": "default"},
        "kwargs": {"batch_size": 50},
    },

    # Application Completion Orchestrator
    "recalculate-stale-app-reviews": {
        "task": "tasks.app_completion_tasks.recalculate_stale_reviews_task",
        "schedule": crontab(hour="*/6"),  # Every 6 hours
        "options": {"queue": "low_priority"},
        "kwargs": {"stale_hours": 24},
    },
    "send-app-completion-reminders": {
        "task": "tasks.app_completion_tasks.send_pending_reminders_task",
        "schedule": crontab(hour="9,14", minute="0"),  # 9 AM and 2 PM daily
        "options": {"queue": "default"},
        "kwargs": {"reminder_delay_hours": 24},
    },
}


# ============================================================================
# Health Check
# ============================================================================

def check_celery_health() -> dict:
    """
    Check Celery/Redis health for readiness probes.

    Returns:
        dict with status, broker connectivity, and worker info
    """
    result = {
        "status": "unknown",
        "broker": "unknown",
        "workers": [],
        "queues": {},
    }

    try:
        # Check broker connectivity
        inspector = celery_app.control.inspect()

        # Check if any workers are active
        active_workers = inspector.active()
        if active_workers:
            result["status"] = "healthy"
            result["broker"] = "connected"
            result["workers"] = list(active_workers.keys())

            # Get queue lengths
            for queue_name in ["default", "high_priority", "low_priority", "ai_tasks"]:
                try:
                    with celery_app.connection() as conn:
                        channel = conn.channel()
                        queue = channel.queue_declare(queue_name, passive=True)
                        result["queues"][queue_name] = queue.message_count
                except Exception as e:
                    logger.warning(f"Error checking queue {queue_name}: {e}")
                    result["queues"][queue_name] = "unknown"
        else:
            result["status"] = "degraded"
            result["broker"] = "connected"
            result["workers"] = []

    except Exception as e:
        result["status"] = "unhealthy"
        result["broker"] = "disconnected"
        result["error"] = str(e)

    return result


def check_redis_health() -> dict:
    """
    Check Redis connectivity directly.

    Returns:
        dict with status and latency info
    """
    import time

    result = {
        "status": "unknown",
        "latency_ms": None,
    }

    try:
        import redis as redis_lib

        redis_url = get_redis_url()
        r = redis_lib.from_url(redis_url)

        start = time.time()
        r.ping()
        latency = (time.time() - start) * 1000

        result["status"] = "healthy"
        result["latency_ms"] = round(latency, 2)

    except Exception as e:
        result["status"] = "unhealthy"
        result["error"] = str(e)

    return result


# ============================================================================
# Task Decorators for Migration
# ============================================================================

def celery_task(name: str = None, **options):
    """
    Decorator to convert existing functions to Celery tasks.

    Usage:
        @celery_task(name="tasks.sla_tasks.update_milestone_statuses_task")
        def update_milestone_statuses_task():
            ...
    """
    def decorator(func):
        return celery_app.task(name=name, **options)(func)
    return decorator


if __name__ == "__main__":
    # Quick health check when run directly
    import json
    print("Celery Health Check")
    print("=" * 50)
    print(json.dumps(check_celery_health(), indent=2))
    print("\nRedis Health Check")
    print("=" * 50)
    print(json.dumps(check_redis_health(), indent=2))
