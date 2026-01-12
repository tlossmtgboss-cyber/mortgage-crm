"""
Background tasks package for the Perennia CRM backend.

Provides:
- agent_tasks: AI agent background tasks
- sla_tasks: SLA monitoring and alerting
- outreach_tasks: Automated outreach tasks
- usage_aggregation_tasks: Daily usage cost aggregation
- calendar_sync_tasks: CRM ↔ Salesforce calendar synchronization
"""

from .usage_aggregation_tasks import (
    run_daily_aggregation,
    aggregate_daily_user_usage,
    aggregate_daily_team_usage,
    aggregate_daily_org_usage,
    backfill_aggregation
)

from .calendar_sync_tasks import (
    push_event_to_salesforce,
    push_event_to_salesforce_sync,
    process_pending_sync_events,
    process_pending_sync_events_sync,
    reconcile_calendar,
    reconcile_calendar_sync,
    check_sync_health,
    check_sync_health_sync,
    register_calendar_sync_jobs
)

__all__ = [
    # Usage aggregation
    "run_daily_aggregation",
    "aggregate_daily_user_usage",
    "aggregate_daily_team_usage",
    "aggregate_daily_org_usage",
    "backfill_aggregation",
    # Calendar sync
    "push_event_to_salesforce",
    "push_event_to_salesforce_sync",
    "process_pending_sync_events",
    "process_pending_sync_events_sync",
    "reconcile_calendar",
    "reconcile_calendar_sync",
    "check_sync_health",
    "check_sync_health_sync",
    "register_calendar_sync_jobs"
]
