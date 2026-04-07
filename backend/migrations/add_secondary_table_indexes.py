"""
Add missing composite indexes on secondary tables for query performance.
=======================================================================

The primary tables (leads, loans) and high-traffic secondary tables (activities,
tasks, sms_messages, email_messages, documents) received composite indexes in
the ``add_performance_indexes`` migration.  This migration covers the remaining
secondary tables that have ``organization_id`` columns but lack composite
indexes on hot query patterns.

Tables covered:
  - activities:           (org, lead_id), (org, loan_id)  -- profile page feeds
  - email_messages:       (org, lead_id), (loan_id, created_at) -- loan email history
  - scheduled_workflows:  (org, is_active), (org, next_run), (user_id, is_active)
  - workflow_executions:  (org, status), (workflow_id, status), (org, started_at)
  - workflows:            (org, is_active), (org, workflow_type)
  - conversations:        (org, user_id), (user_id, created_at)
  - conversation_memory:  (org, user_id), (org, lead_id)
  - conversation_sessions:(org, user_id), (org, is_active)
  - ai_audit_logs:        (org, created_at), (org, agent_name), (org, action_type)
  - ai_actions:           (org, status), (org, created_at), (user_id, status)
  - ai_colleague_actions: (org, agent_name), (org, status, created_at)
  - ai_delegated_tasks:   (org, user_id), (org, is_active)
  - ai_feedback_logs:     (org, status), (org, created_at)
  - ai_knowledge_base:    (org, category), (org, is_active)
  - voicemail_drops:      (org, status), (org, created_at), (campaign_id, status)
  - voicemail_campaigns:  (org, status), (org, scheduled_at)
  - voicemail_templates:  (org, category), (org, is_active)
  - sms_conversations:    (org, lead_id), (org, last_message_at)
  - email_drafts:         (org, status), (org, created_at)
  - email_intakes:        (org, received_at), (org, match_status)
  - attachment_intakes:   (org, classification_status)
  - emails:               (org, lead_id)
  - integration_logs:     (org, created_at), (org, integration_type)
  - escalation_records:   (org, status), (org, created_at)
  - handoff_logs:         (org, handoff_at)
  - teams_messages:       (org, created_at)
  - channel_preferences:  (org, lead_id)
  - scheduler_blocked_times: (org, user_id, start_datetime)

All indexes use IF NOT EXISTS for idempotent re-runs.

Usage:
    python -m migrations.add_secondary_table_indexes
    python -c "from migrations.add_secondary_table_indexes import run_migration; run_migration()"
"""

import logging

logger = logging.getLogger(__name__)

# Each entry: (index_name, table, columns)
INDEXES = [
    # ==========================================================================
    # ACTIVITIES -- profile page activity feeds need org+lead and org+loan
    # Existing composites: lead+created, loan+created, org+created, org+type,
    #   user+created.  Missing: org+lead_id, org+loan_id for RLS-filtered
    #   profile page queries that don't sort by time.
    # ==========================================================================
    ("ix_activities_org_lead", "activities", "organization_id, lead_id"),
    ("ix_activities_org_loan", "activities", "organization_id, loan_id"),

    # ==========================================================================
    # EMAIL_MESSAGES -- loan email history and org+lead lookup
    # Existing composites: lead+created, org+created.
    # Missing: org+lead for RLS-filtered lead profile, loan+created for loan
    # communication timeline.
    # ==========================================================================
    ("ix_email_messages_org_lead", "email_messages", "organization_id, lead_id"),
    ("ix_email_messages_loan_created", "email_messages", "loan_id, created_at"),

    # ==========================================================================
    # SCHEDULED_WORKFLOWS -- workflow list pages, scheduler polling
    # Existing: single-column on org_id, user_id, next_run, is_active.
    # Missing: all composites.
    # ==========================================================================
    ("ix_sched_wf_org_active", "scheduled_workflows", "organization_id, is_active"),
    ("ix_sched_wf_org_next_run", "scheduled_workflows", "organization_id, next_run"),
    ("ix_sched_wf_user_active", "scheduled_workflows", "user_id, is_active"),

    # ==========================================================================
    # WORKFLOW_EXECUTIONS -- execution history, status dashboards
    # Existing: single-column on org_id, workflow_id.
    # Missing: all composites.
    # ==========================================================================
    ("ix_wf_exec_org_status", "workflow_executions", "organization_id, status"),
    ("ix_wf_exec_wf_status", "workflow_executions", "workflow_id, status"),
    ("ix_wf_exec_org_started", "workflow_executions", "organization_id, started_at"),

    # ==========================================================================
    # WORKFLOWS -- workflow management pages
    # Existing: single-column on org_id.
    # Missing: org+active, org+type.
    # ==========================================================================
    ("ix_workflows_org_active", "workflows", "organization_id, is_active"),
    ("ix_workflows_org_type", "workflows", "organization_id, workflow_type"),

    # ==========================================================================
    # CONVERSATIONS -- AI chat history per user
    # Existing: single-column on org_id.
    # Missing: org+user for loading chat history, user+created for timeline.
    # ==========================================================================
    ("ix_conversations_org_user", "conversations", "organization_id, user_id"),
    ("ix_conversations_user_created", "conversations", "user_id, created_at"),

    # ==========================================================================
    # CONVERSATION_MEMORY -- AI context retrieval
    # Existing: single-column on org_id, user_id, lead_id, loan_id.
    # Missing: org+user, org+lead composites for RLS-filtered lookups.
    # ==========================================================================
    ("ix_conv_memory_org_user", "conversation_memory", "organization_id, user_id"),
    ("ix_conv_memory_org_lead", "conversation_memory", "organization_id, lead_id"),

    # ==========================================================================
    # CONVERSATION_SESSIONS -- active session lookup
    # Existing: single-column on user_id, org_id, is_active.
    # Missing: org+user, org+active composites.
    # ==========================================================================
    ("ix_conv_session_org_user", "conversation_sessions", "organization_id, user_id"),
    ("ix_conv_session_org_active", "conversation_sessions", "organization_id, is_active"),

    # ==========================================================================
    # AI_AUDIT_LOGS -- audit dashboards, agent performance views
    # Existing: single-column on org_id, user_id, agent_name, action_type,
    #   session_id, created_at.
    # Missing: org+created (time-series dashboard), org+agent, org+action_type.
    # ==========================================================================
    ("ix_ai_audit_org_created", "ai_audit_logs", "organization_id, created_at"),
    ("ix_ai_audit_org_agent", "ai_audit_logs", "organization_id, agent_name"),
    ("ix_ai_audit_org_action_type", "ai_audit_logs", "organization_id, action_type"),

    # ==========================================================================
    # AI_ACTIONS -- approval queue, action history
    # Existing: single-column on org_id, action_type, created_at.
    # Missing: org+status (approval queue), org+created (time-series),
    #   user+status (my pending approvals).
    # ==========================================================================
    ("ix_ai_actions_org_status", "ai_actions", "organization_id, status"),
    ("ix_ai_actions_org_created", "ai_actions", "organization_id, created_at"),
    ("ix_ai_actions_user_status", "ai_actions", "user_id, status"),

    # ==========================================================================
    # AI_COLLEAGUE_ACTIONS -- Mission Control dashboard
    # Existing: single-column on org_id, action_id, agent_name, action_type,
    #   status, created_at.
    # Missing: org+agent (agent-specific views), org+status+created
    #   (recent actions by status).
    # ==========================================================================
    ("ix_ai_colleague_org_agent", "ai_colleague_actions", "organization_id, agent_name"),
    ("ix_ai_colleague_org_status_created", "ai_colleague_actions", "organization_id, status, created_at"),

    # ==========================================================================
    # AI_DELEGATED_TASKS -- delegation management
    # Existing: single-column on org_id.
    # Missing: org+user, org+active.
    # ==========================================================================
    ("ix_ai_deleg_org_user", "ai_delegated_tasks", "organization_id, user_id"),
    ("ix_ai_deleg_org_active", "ai_delegated_tasks", "organization_id, is_active"),

    # ==========================================================================
    # AI_FEEDBACK_LOGS -- feedback review dashboard
    # Existing: single-column on user_id, created_at, status, category, org_id.
    # Missing: org+status (pending review queue), org+created (time-series).
    # ==========================================================================
    ("ix_ai_feedback_org_status", "ai_feedback_logs", "organization_id, status"),
    ("ix_ai_feedback_org_created", "ai_feedback_logs", "organization_id, created_at"),

    # ==========================================================================
    # AI_KNOWLEDGE_BASE -- knowledge search within org
    # Existing: single-column on category, is_active, title, org_id.
    # Missing: org+category, org+active.
    # ==========================================================================
    ("ix_ai_kb_org_category", "ai_knowledge_base", "organization_id, category"),
    ("ix_ai_kb_org_active", "ai_knowledge_base", "organization_id, is_active"),

    # ==========================================================================
    # VOICEMAIL_DROPS -- voicemail delivery tracking, campaign views
    # Existing: single-column on org_id, lead_id, loan_id, user_id,
    #   campaign_id, template_id, vapi_call_id, rvm_session_id, created_at.
    # Missing: org+status, org+created, campaign+status.
    # ==========================================================================
    ("ix_vm_drops_org_status", "voicemail_drops", "organization_id, status"),
    ("ix_vm_drops_org_created", "voicemail_drops", "organization_id, created_at"),
    ("ix_vm_drops_campaign_status", "voicemail_drops", "campaign_id, status"),

    # ==========================================================================
    # VOICEMAIL_CAMPAIGNS -- campaign management list
    # Existing: single-column on org_id, user_id, status, scheduled_at.
    # Missing: org+status, org+scheduled.
    # ==========================================================================
    ("ix_vm_campaigns_org_status", "voicemail_campaigns", "organization_id, status"),
    ("ix_vm_campaigns_org_scheduled", "voicemail_campaigns", "organization_id, scheduled_at"),

    # ==========================================================================
    # VOICEMAIL_TEMPLATES -- template picker filtered by org
    # Existing: single-column on org_id, user_id, category, is_active.
    # Missing: org+category, org+active.
    # ==========================================================================
    ("ix_vm_templates_org_category", "voicemail_templates", "organization_id, category"),
    ("ix_vm_templates_org_active", "voicemail_templates", "organization_id, is_active"),

    # ==========================================================================
    # SMS_CONVERSATIONS -- inbox views, lead SMS lookup
    # Existing: single-column on phone_number, user_id, is_active, org_id.
    # Missing: org+lead for RLS-filtered lead SMS, org+last_message for inbox
    #   sorted by recency.
    # ==========================================================================
    ("ix_sms_conv_org_lead", "sms_conversations", "organization_id, lead_id"),
    ("ix_sms_conv_org_last_msg", "sms_conversations", "organization_id, last_message_at"),

    # ==========================================================================
    # EMAIL_DRAFTS -- draft management views
    # Existing: single-column on org_id, user_id, lead_id, loan_id,
    #   recipient_email, status, created_at.
    # Missing: org+status (draft list), org+created (timeline).
    # ==========================================================================
    ("ix_email_drafts_org_status", "email_drafts", "organization_id, status"),
    ("ix_email_drafts_org_created", "email_drafts", "organization_id, created_at"),

    # ==========================================================================
    # EMAIL_INTAKES -- document intake queue
    # Existing: single-column on match_status, received_at, org_id.
    # Missing: org+received (time-sorted inbox), org+match_status (queue filter).
    # ==========================================================================
    ("ix_email_intakes_org_received", "email_intakes", "organization_id, received_at"),
    ("ix_email_intakes_org_match", "email_intakes", "organization_id, match_status"),

    # ==========================================================================
    # ATTACHMENT_INTAKES -- classification queue
    # Existing: single-column on classification_status, email_intake_id, org_id.
    # Missing: org+classification_status (filtered queue).
    # ==========================================================================
    ("ix_attach_intakes_org_class", "attachment_intakes", "organization_id, classification_status"),

    # ==========================================================================
    # EMAILS (Graph API) -- email intelligence per lead
    # Existing composites: org+received (partial on unprocessed), org+user.
    # Missing: org+lead for lead-specific email view.
    # ==========================================================================
    ("ix_emails_org_lead", "emails", "organization_id, lead_id"),

    # ==========================================================================
    # INTEGRATION_LOGS -- integration health monitoring
    # Existing: single-column on org_id.
    # Missing: org+created (time-series), org+type (per-integration view).
    # ==========================================================================
    ("ix_integ_logs_org_created", "integration_logs", "organization_id, created_at"),
    ("ix_integ_logs_org_type", "integration_logs", "organization_id, integration_type"),

    # ==========================================================================
    # ESCALATION_RECORDS -- escalation dashboard
    # Existing: single-column on org_id, status, escalation_level, loan_id.
    # Missing: org+status (queue), org+created (timeline).
    # ==========================================================================
    ("ix_escalation_org_status", "escalation_records", "organization_id, status"),
    ("ix_escalation_org_created", "escalation_records", "organization_id, created_at"),

    # ==========================================================================
    # HANDOFF_LOGS -- agent handoff analytics
    # Existing: single-column on org_id, session_id.
    # Missing: org+handoff_at (time-series).
    # ==========================================================================
    ("ix_handoff_org_time", "handoff_logs", "organization_id, handoff_at"),

    # ==========================================================================
    # TEAMS_MESSAGES -- Teams inbox
    # Existing: single-column on org_id.
    # Missing: org+created (time-series inbox view).
    # ==========================================================================
    ("ix_teams_msg_org_created", "teams_messages", "organization_id, created_at"),

    # ==========================================================================
    # CHANNEL_PREFERENCES -- lead preference lookup with RLS
    # Existing: single-column on user_id, lead_id, org_id.
    # Missing: org+lead composite for RLS-filtered lead preference lookup.
    # ==========================================================================
    ("ix_channel_pref_org_lead", "channel_preferences", "organization_id, lead_id"),

    # ==========================================================================
    # SCHEDULER_BLOCKED_TIMES -- user schedule conflict checks
    # Existing: single-column on org_id, composite start+end range.
    # Missing: org+user+start for per-user blocked-time lookups.
    # ==========================================================================
    ("ix_blocked_times_org_user_start", "scheduler_blocked_times", "organization_id, user_id, start_datetime"),
]


def run_migration(engine=None):
    """Create composite indexes on secondary tables.

    Tries CONCURRENTLY first (avoids write locks on large tables) and falls
    back to a regular CREATE INDEX when CONCURRENTLY fails (e.g. inside an
    existing transaction).
    """
    from sqlalchemy import text

    if engine is None:
        from db import engine as _engine
        engine = _engine

    created = 0
    skipped = 0
    errors = 0

    for idx_name, table, columns in INDEXES:
        # --- Attempt 1: CONCURRENTLY (no lock, but can't run in a txn) -------
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                    f"{idx_name} ON {table} ({columns})"
                ))
                conn.commit()
            created += 1
            logger.info("Created index %s on %s(%s) [concurrent]", idx_name, table, columns)
            continue
        except Exception:
            pass  # fall through to non-concurrent attempt

        # --- Attempt 2: regular CREATE INDEX (holds lock briefly) -------------
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"{idx_name} ON {table} ({columns})"
                ))
                conn.commit()
            created += 1
            logger.info("Created index %s on %s(%s)", idx_name, table, columns)
        except Exception as e:
            err_msg = str(e)
            if "already exists" in err_msg.lower():
                skipped += 1
                logger.info("Index %s already exists, skipping", idx_name)
            else:
                errors += 1
                logger.warning("Index %s on %s skipped: %s", idx_name, table, err_msg)

    logger.info(
        "Secondary table index migration complete: "
        "%d created, %d skipped, %d errors",
        created, skipped, errors,
    )
    return {"created": created, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_migration()
    print(f"\nResult: {result}")
