"""
Performance Index Migration
============================

Adds missing composite and single-column indexes to hot tables for common
query patterns identified via code audit.

Tables covered:
  - leads: last_contact, ai_score, source, loan_number, salesforce_id
  - loans: borrower_name, closing_date, stage_changed_at, lock_expiration_date,
           loan_type, application_date; partial index on active loans
  - activities: (loan_id, created_at), (organization_id, type)
  - documents: (loan_id, status), (borrower_id, status)
  - compliance_alerts: (loan_id, status), (organization_id, severity),
                       (organization_id, alert_type), deadline_date
  - calendar_events: (user_id, start_time), (organization_id, start_time)
  - ai_tasks: (assigned_to_id, type), (organization_id, assigned_to_id)
  - tasks: (organization_id, due_date), (owner_id, due_date)
  - sms_messages: (lead_id, created_at), (loan_id, created_at), (organization_id, created_at)
  - email_messages: (lead_id, created_at), (organization_id, created_at)
  - stage_history: (organization_id, changed_at), (entity_type, entity_id, changed_at)

All indexes use IF NOT EXISTS for idempotent re-runs.

Usage:
    python -m migrations.add_performance_indexes          # uses DATABASE_URL
    python -c "from migrations.add_performance_indexes import run_migration; run_migration()"
"""

import logging

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Create performance indexes on hot tables."""
    from sqlalchemy import text

    if engine is None:
        from db import engine as _engine
        engine = _engine

    # Each entry: (index_name, table, columns, condition_or_None)
    indexes = [
        # =====================================================================
        # LEADS — hot table, queried on every dashboard load
        # =====================================================================
        # Existing: ix_leads_owner_id, ix_leads_stage, ix_leads_created_at,
        #   ix_leads_referral_partner_id, ix_leads_owner_stage,
        #   ix_leads_organization_id, ix_leads_org_stage, ix_leads_org_created

        # Follow-up queries sort/filter by last_contact
        ("ix_leads_last_contact", "leads", "last_contact", None),

        # AI scoring queries filter/sort by ai_score
        ("ix_leads_ai_score", "leads", "ai_score", None),

        # Source breakdown on dashboard
        ("ix_leads_source", "leads", "source", None),

        # Lead-to-loan join via loan_number
        ("ix_leads_loan_number", "leads", "loan_number", None),

        # Salesforce sync lookups
        ("ix_leads_salesforce_id", "leads", "salesforce_id", None),

        # Owner + last_contact for stale-lead reports
        ("ix_leads_owner_last_contact", "leads", "owner_id, last_contact", None),

        # Org + source for source breakdown by org
        ("ix_leads_org_source", "leads", "organization_id, source", None),

        # Org + ai_score for AI-scored lead lists
        ("ix_leads_org_ai_score", "leads", "organization_id, ai_score", None),

        # =====================================================================
        # LOANS — hot table, queried on every dashboard + pipeline view
        # =====================================================================
        # Existing: ix_loans_loan_officer_id, ix_loans_stage, ix_loans_funded_date,
        #   ix_loans_created_at, ix_loans_officer_stage, ix_loans_organization_id,
        #   ix_loans_org_stage, ix_loans_org_created

        # Borrower search (text search, LIKE queries)
        ("ix_loans_borrower_name", "loans", "borrower_name", None),

        # Closing pipeline: closing_date filter + sort
        ("ix_loans_closing_date", "loans", "closing_date", None),

        # Pipeline aging: stage_changed_at sort
        ("ix_loans_stage_changed_at", "loans", "stage_changed_at", None),

        # Rate lock alerts: lock_expiration_date filter
        ("ix_loans_lock_expiration_date", "loans", "lock_expiration_date", None),

        # Loan type breakdown
        ("ix_loans_loan_type", "loans", "loan_type", None),

        # Application date for funnel/conversion queries
        ("ix_loans_application_date", "loans", "application_date", None),

        # Composite: org + closing_date for closing pipeline by org
        ("ix_loans_org_closing_date", "loans", "organization_id, closing_date", None),

        # Composite: org + funded_date for production reports
        ("ix_loans_org_funded_date", "loans", "organization_id, funded_date", None),

        # Composite: LO + funded_date for LO production ranking
        ("ix_loans_lo_funded_date", "loans", "loan_officer_id, funded_date", None),

        # Composite: org + lock_expiration for lock alert queries
        ("ix_loans_org_lock_exp", "loans", "organization_id, lock_expiration_date", None),

        # Partial: active pipeline only (excludes terminal stages)
        # This covers the most common pipeline query pattern
        (
            "ix_loans_active_pipeline",
            "loans",
            "organization_id, stage, loan_officer_id",
            "stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')",
        ),

        # =====================================================================
        # ACTIVITIES — very high volume table
        # =====================================================================
        # Existing: ix_activities_lead_id, ix_activities_loan_id,
        #   ix_activities_user_id, ix_activities_created_at,
        #   ix_activities_lead_created, ix_activities_organization_id,
        #   ix_activities_org_created

        # Loan activity timeline
        ("ix_activities_loan_created", "activities", "loan_id, created_at", None),

        # Activity type dashboards within org
        ("ix_activities_org_type", "activities", "organization_id, type", None),

        # User activity timeline
        ("ix_activities_user_created", "activities", "user_id, created_at", None),

        # =====================================================================
        # DOCUMENTS — queried per-loan in pipeline views
        # =====================================================================
        # Existing: ix_documents_borrower_id, ix_documents_loan_id,
        #   ix_documents_doc_type, ix_documents_organization_id

        # Active documents per loan (most common query)
        ("ix_documents_loan_status", "documents", "loan_id, status", None),

        # Active documents per borrower
        ("ix_documents_borrower_status", "documents", "borrower_id, status", None),

        # Org + status for compliance overview
        ("ix_documents_org_status", "documents", "organization_id, status", None),

        # =====================================================================
        # COMPLIANCE_ALERTS — queried by compliance dashboard + per-loan
        # =====================================================================
        # Existing: ix_compliance_alerts_loan_id, ix_compliance_alerts_org_id,
        #   ix_compliance_alerts_status

        # Loan + status composite for per-loan compliance view
        ("ix_compliance_alerts_loan_status", "compliance_alerts", "loan_id, status", None),

        # Org + severity for compliance dashboard priority sort
        ("ix_compliance_alerts_org_severity", "compliance_alerts", "organization_id, severity", None),

        # Org + alert_type for compliance breakdown by type
        ("ix_compliance_alerts_org_type", "compliance_alerts", "organization_id, alert_type", None),

        # Deadline tracking
        ("ix_compliance_alerts_deadline", "compliance_alerts", "deadline_date", None),

        # Open alerts with deadline (the hot compliance query)
        (
            "ix_compliance_alerts_open_deadline",
            "compliance_alerts",
            "organization_id, deadline_date",
            "status = 'open'",
        ),

        # =====================================================================
        # CALENDAR_EVENTS — queried for calendar views
        # =====================================================================
        # No existing composite indexes

        # User calendar view (most common)
        ("ix_calendar_events_user_start", "calendar_events", "user_id, start_time", None),

        # Org calendar view
        ("ix_calendar_events_org_start", "calendar_events", "organization_id, start_time", None),

        # Status filtering
        ("ix_calendar_events_status", "calendar_events", "status", None),

        # =====================================================================
        # AI_TASKS — queried in command center + task panels
        # =====================================================================
        # Existing: ix_ai_tasks_assigned_to_id, ix_ai_tasks_lead_id,
        #   ix_ai_tasks_loan_id, ix_ai_tasks_due_date, ix_ai_tasks_organization_id

        # Assigned tasks by type (for task categorization)
        ("ix_ai_tasks_assigned_type", "ai_tasks", "assigned_to_id, type", None),

        # Org + assigned for team task views
        ("ix_ai_tasks_org_assigned", "ai_tasks", "organization_id, assigned_to_id", None),

        # =====================================================================
        # TASKS — queried in dashboard task panel + workflow SLA views
        # =====================================================================
        # Existing: ix_tasks_owner_id, ix_tasks_status, ix_tasks_due_date,
        #   ix_tasks_lead_id, ix_tasks_loan_id, ix_tasks_owner_status,
        #   ix_tasks_organization_id, ix_tasks_org_status

        # Org + due_date for SLA task sorting
        ("ix_tasks_org_due_date", "tasks", "organization_id, due_date", None),

        # Owner + due_date for personal task list sorted by due date
        ("ix_tasks_owner_due_date", "tasks", "owner_id, due_date", None),

        # Pending tasks with due date (the hot dashboard query)
        (
            "ix_tasks_pending_due",
            "tasks",
            "owner_id, due_date",
            "status = 'pending'",
        ),

        # =====================================================================
        # SMS_MESSAGES — queried for conversation history
        # =====================================================================
        # No existing composite indexes

        # Lead SMS history
        ("ix_sms_messages_lead_created", "sms_messages", "lead_id, created_at", None),

        # Loan SMS history
        ("ix_sms_messages_loan_created", "sms_messages", "loan_id, created_at", None),

        # Org SMS overview sorted by time
        ("ix_sms_messages_org_created", "sms_messages", "organization_id, created_at", None),

        # =====================================================================
        # EMAIL_MESSAGES — queried for communication history
        # =====================================================================
        # No existing composite indexes

        # Lead email history
        ("ix_email_messages_lead_created", "email_messages", "lead_id, created_at", None),

        # Org email overview sorted by time
        ("ix_email_messages_org_created", "email_messages", "organization_id, created_at", None),

        # =====================================================================
        # STAGE_HISTORY — queried for audit trails + analytics
        # =====================================================================
        # Existing: ix_stage_history_lead_id, ix_stage_history_loan_id,
        #   ix_stage_history_changed_at, ix_stage_history_entity,
        #   ix_stage_history_organization_id

        # Org + changed_at for org-wide stage change audit
        ("ix_stage_history_org_changed", "stage_history", "organization_id, changed_at", None),

        # Entity timeline (entity_type + entity_id + changed_at)
        ("ix_stage_history_entity_timeline", "stage_history", "entity_type, entity_id, changed_at", None),

        # =====================================================================
        # EMAILS (fetched from Graph API) — queried for email intelligence
        # =====================================================================
        # Existing column indexes: message_id, sender_email, received_date, processed

        # Unprocessed emails (the hot background job query)
        (
            "ix_emails_unprocessed",
            "emails",
            "organization_id, received_date",
            "processed = false",
        ),

        # Org + user for per-user email view
        ("ix_emails_org_user", "emails", "organization_id, user_id", None),
    ]

    created = 0
    skipped = 0
    errors = 0

    with engine.connect() as conn:
        for name, table, cols, condition in indexes:
            try:
                where_clause = f" WHERE {condition}" if condition else ""
                sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols}){where_clause}"
                conn.execute(text(sql))
                created += 1
                logger.info(f"Created index {name} on {table}({cols})")
            except Exception as e:
                err_msg = str(e)
                if "already exists" in err_msg.lower():
                    skipped += 1
                    logger.info(f"Index {name} already exists, skipping")
                else:
                    errors += 1
                    logger.warning(f"Index {name} failed: {err_msg}")
        conn.commit()

    logger.info(
        f"Performance index migration complete: "
        f"{created} created, {skipped} skipped, {errors} errors"
    )
    return {"created": created, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_migration()
    print(f"\nResult: {result}")
