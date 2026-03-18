"""
Add performance indexes for scheduler queries.

These indexes target the most common query patterns in the scheduler module
that currently rely on sequential scans or suboptimal index usage:

1. Appointment analytics/no-show detection: (organization_id, status, scheduled_start)
2. Attendee history lookups (no-show risk, duplicate detection): (attendee_email, organization_id, status)
3. SchedulerConfig settings lookup: (user_id, organization_id) composite
4. BlockedTime slot generation: (user_id, organization_id, start_datetime)
5. CalendarEvent cross-source conflict detection: (user_id, status, start_time)
6. CRMCalendarEvent cross-source conflict detection: (owner_user_id, organization_id, start_at)
7. Legacy ScheduledAppointment cross-source conflicts: (loan_officer_id, organization_id, status, start_time)
8. WebhookDeliveryLog health checks: (subscription_id, status, created_at) composite
9. RecurringAvailability org-scoped lookup: (user_id, organization_id, is_active)

All indexes use IF NOT EXISTS to be safely re-runnable.
CONCURRENTLY is used to avoid locking tables during creation.

Run with: python -m migrations.add_scheduler_performance_indexes
"""
import logging
import sys

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Each entry: (index_name, table, columns, description)
# Kept as raw SQL so CONCURRENTLY and IF NOT EXISTS work correctly.
INDEXES = [
    # --- scheduler_appointments ---
    # Analytics queries filter by org + status + date range (overview, trends, no-show batch)
    (
        "idx_appointments_status_schedule",
        "scheduler_appointments",
        "(organization_id, status, scheduled_start)",
        "Analytics and no-show detection queries",
    ),
    # No-show risk scoring queries attendee_email + org + status (ai_scheduling.py _calculate_no_show_risk)
    # Also speeds up duplicate booking detection (_check_duplicate_booking)
    (
        "idx_appointments_attendee_org_status",
        "scheduler_appointments",
        "(attendee_email, organization_id, status)",
        "Attendee history lookups for no-show risk and duplicate detection",
    ),

    # --- scheduler_configs ---
    # Every settings lookup queries (user_id, organization_id); currently only separate indexes exist
    (
        "idx_scheduler_configs_user_org",
        "scheduler_configs",
        "(user_id, organization_id)",
        "Settings lookup in _get_user_timezone and slot generation",
    ),

    # --- scheduler_blocked_times ---
    # Slot generation queries blocked times by user + org + time range
    (
        "idx_blocked_times_user_org_start",
        "scheduler_blocked_times",
        "(user_id, organization_id, start_datetime)",
        "Slot generation blocked time filtering",
    ),

    # --- calendar_events ---
    # Cross-source conflict detection queries by user_id + status + start_time
    # Currently has no composite index at all
    (
        "idx_calendar_events_user_status_start",
        "calendar_events",
        "(user_id, status, start_time)",
        "Cross-source conflict detection in _get_cross_source_conflicts",
    ),

    # --- crm_calendar_events ---
    # Cross-source conflict detection queries owner_user_id + org + start_at
    # Existing idx_calendar_owner_start is (owner_user_id, start_at) without org_id
    (
        "idx_crm_cal_events_owner_org_start",
        "crm_calendar_events",
        "(owner_user_id, organization_id, start_at)",
        "Org-scoped cross-source conflict detection",
    ),

    # --- scheduled_appointments (legacy) ---
    # Legacy cross-source conflict detection queries LO + org + status + start_time
    (
        "idx_sched_appts_lo_org_status_start",
        "scheduled_appointments",
        "(loan_officer_id, organization_id, status, start_time)",
        "Legacy cross-source conflict detection",
    ),

    # --- webhook_delivery_logs ---
    # Health check queries filter by subscription + status + time range
    # Existing ix_webhook_log_status is (subscription_id, status) without created_at
    (
        "idx_webhook_logs_sub_status_created",
        "webhook_delivery_logs",
        "(subscription_id, status, created_at)",
        "Webhook health check queries with time range filtering",
    ),

    # --- recurring_availability ---
    # Slot generation checks for active rows per user + org
    # Existing ix_recur_avail_active is (user_id, is_active) without org_id
    (
        "idx_recur_avail_user_org_active",
        "recurring_availability",
        "(user_id, organization_id, is_active)",
        "Org-scoped active availability lookup in slot generation",
    ),
]


def run():
    """Create all performance indexes, skipping any that already exist."""
    # Import here to avoid issues when module is loaded outside the app context
    from db import get_engine

    engine = get_engine()
    created = 0
    skipped = 0
    failed = 0

    for idx_name, table, columns, description in INDEXES:
        sql = f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} {columns}"
        try:
            # CONCURRENTLY cannot run inside a transaction block,
            # so we use raw connection with autocommit (DBAPI-level).
            with engine.connect() as conn:
                # SQLAlchemy 2.x: use conn.execution_options(isolation_level="AUTOCOMMIT")
                # SQLAlchemy 1.x: set on the underlying DBAPI connection
                try:
                    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                except Exception:
                    # Fallback for older SQLAlchemy: set autocommit on raw connection
                    raw = conn.connection
                    raw.autocommit = True

                conn.execute(text(sql))
                logger.info(f"[OK] {idx_name} on {table} -- {description}")
                created += 1
        except Exception as e:
            err_msg = str(e).lower()
            if "does not exist" in err_msg:
                # Table doesn't exist yet (e.g., feature not deployed) -- skip gracefully
                logger.info(f"[SKIP] {idx_name} -- table {table} does not exist")
                skipped += 1
            elif "already exists" in err_msg:
                logger.info(f"[SKIP] {idx_name} -- already exists")
                skipped += 1
            else:
                logger.warning(f"[FAIL] {idx_name} on {table}: {e}")
                failed += 1

    logger.info(f"Done: {created} created, {skipped} skipped, {failed} failed")
    return created, skipped, failed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    created, skipped, failed = run()
    sys.exit(1 if failed > 0 else 0)
