"""
Background tasks package for the Perennia CRM backend.

Provides:
- agent_tasks: AI agent background tasks
- sla_tasks: SLA monitoring and alerting
- outreach_tasks: Automated outreach tasks
- usage_aggregation_tasks: Daily usage cost aggregation
- calendar_sync_tasks: CRM ↔ Salesforce calendar synchronization
- salesforce_sync_tasks: Salesforce email, calendar, and data sync
"""

from .usage_aggregation_tasks import (
    run_daily_aggregation,
    aggregate_daily_user_usage,
    aggregate_daily_team_usage,
    aggregate_daily_org_usage,
    backfill_aggregation
)

from .calendar_sync_tasks import (
    # Phase 1: Push (CRM → Salesforce)
    push_event_to_salesforce,
    push_event_to_salesforce_sync,
    process_pending_sync_events,
    process_pending_sync_events_sync,
    # Phase 2: Pull (Salesforce → CRM)
    poll_salesforce_events,
    poll_salesforce_events_sync,
    sync_user_calendar,
    sync_user_calendar_sync,
    # Maintenance
    reconcile_calendar,
    reconcile_calendar_sync,
    check_sync_health,
    check_sync_health_sync,
    register_calendar_sync_jobs
)

from .salesforce_sync_tasks import (
    # Email sync
    sync_emails_from_salesforce,
    sync_emails_from_salesforce_sync,
    push_emails_to_salesforce,
    push_emails_to_salesforce_sync,
    # Calendar sync
    sync_calendar_from_salesforce,
    sync_calendar_from_salesforce_sync,
    # All users sync
    sync_all_users_salesforce,
    sync_all_users_salesforce_sync,
    # Health check
    check_salesforce_sync_health,
    check_salesforce_sync_health_sync,
    # Manual trigger
    trigger_user_sync,
    trigger_user_sync_sync,
    # Scheduler registration
    register_salesforce_sync_jobs
)

__all__ = [
    # Usage aggregation
    "run_daily_aggregation",
    "aggregate_daily_user_usage",
    "aggregate_daily_team_usage",
    "aggregate_daily_org_usage",
    "backfill_aggregation",
    # Calendar sync - Phase 1 (Push)
    "push_event_to_salesforce",
    "push_event_to_salesforce_sync",
    "process_pending_sync_events",
    "process_pending_sync_events_sync",
    # Calendar sync - Phase 2 (Pull)
    "poll_salesforce_events",
    "poll_salesforce_events_sync",
    "sync_user_calendar",
    "sync_user_calendar_sync",
    # Calendar sync - Maintenance
    "reconcile_calendar",
    "reconcile_calendar_sync",
    "check_sync_health",
    "check_sync_health_sync",
    "register_calendar_sync_jobs",
    # Salesforce sync - Email
    "sync_emails_from_salesforce",
    "sync_emails_from_salesforce_sync",
    "push_emails_to_salesforce",
    "push_emails_to_salesforce_sync",
    # Salesforce sync - Calendar
    "sync_calendar_from_salesforce",
    "sync_calendar_from_salesforce_sync",
    # Salesforce sync - All users
    "sync_all_users_salesforce",
    "sync_all_users_salesforce_sync",
    # Salesforce sync - Health & Manual trigger
    "check_salesforce_sync_health",
    "check_salesforce_sync_health_sync",
    "trigger_user_sync",
    "trigger_user_sync_sync",
    "register_salesforce_sync_jobs"
]
