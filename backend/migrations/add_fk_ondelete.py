"""
Migration: Add explicit ondelete behavior to FK constraints.

Enterprise Readiness Check 3.7: FK ondelete behavior is undefined on most
ForeignKey declarations. PostgreSQL defaults to NO ACTION which can cause
cascade issues and orphaned rows.

This migration drops the old FK constraints and recreates them with explicit
ondelete behavior (CASCADE or SET NULL) based on the relationship semantics.

Rules applied:
  - organization_id -> CASCADE (delete org = delete all org data)
  - user_id / owner_id / assigned_to -> SET NULL (unassign, keep the record)
  - lead_id -> CASCADE (delete lead = delete associated records)
  - loan_id -> CASCADE (delete loan = delete associated records)
  - referral_partner_id -> SET NULL (partner deleted = unlink)
  - template_id / config references -> SET NULL (template deleted = unlink)
  - parent_id (self-referential) -> SET NULL

Exceptions:
  - nullable=False user FKs -> CASCADE (record can't exist without the user)
  - Message logs (sms_messages, email_messages, etc.) lead/loan -> SET NULL
    (preserve message history even if lead/loan is deleted)

Usage:
    python -m migrations.add_fk_ondelete
    # or: .venv/bin/python3 migrations/add_fk_ondelete.py
"""

import os
import sys
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Each entry: (table, column, referenced_table, referenced_column, ondelete)
FK_UPDATES = [
    # ========================================================================
    # lead_loan.py — Lead model
    # ========================================================================
    ("leads", "organization_id", "organizations", "id", "CASCADE"),
    ("leads", "referral_partner_id", "referral_partners", "id", "SET NULL"),
    ("leads", "owner_id", "users", "id", "SET NULL"),

    # ========================================================================
    # lead_loan.py — Loan model
    # ========================================================================
    ("loans", "organization_id", "organizations", "id", "CASCADE"),
    ("loans", "loan_officer_id", "users", "id", "SET NULL"),

    # ========================================================================
    # task.py — AITask model
    # ========================================================================
    ("ai_tasks", "organization_id", "organizations", "id", "CASCADE"),
    ("ai_tasks", "lead_id", "leads", "id", "CASCADE"),
    ("ai_tasks", "loan_id", "loans", "id", "CASCADE"),
    ("ai_tasks", "assigned_to_id", "users", "id", "SET NULL"),

    # ========================================================================
    # task.py — Task model
    # ========================================================================
    ("tasks", "organization_id", "organizations", "id", "CASCADE"),
    ("tasks", "owner_id", "users", "id", "SET NULL"),
    ("tasks", "lead_id", "leads", "id", "CASCADE"),
    ("tasks", "loan_id", "loans", "id", "CASCADE"),
    ("tasks", "email_intake_id", "email_intakes", "id", "SET NULL"),

    # ========================================================================
    # task.py — EscalationRecord model
    # ========================================================================
    ("escalation_records", "organization_id", "organizations", "id", "CASCADE"),
    ("escalation_records", "task_id", "tasks", "id", "SET NULL"),
    ("escalation_records", "loan_id", "loans", "id", "CASCADE"),
    ("escalation_records", "lead_id", "leads", "id", "CASCADE"),
    ("escalation_records", "original_owner_id", "users", "id", "SET NULL"),
    ("escalation_records", "escalated_to_id", "users", "id", "SET NULL"),
    ("escalation_records", "acknowledged_by_id", "users", "id", "SET NULL"),
    ("escalation_records", "resolved_by_id", "users", "id", "SET NULL"),
    ("escalation_records", "parent_escalation_id", "escalation_records", "id", "SET NULL"),

    # ========================================================================
    # task.py — HandoffLog model
    # ========================================================================
    ("handoff_logs", "organization_id", "organizations", "id", "CASCADE"),
    ("handoff_logs", "from_user_id", "users", "id", "SET NULL"),
    ("handoff_logs", "to_user_id", "users", "id", "SET NULL"),

    # ========================================================================
    # core.py — Branch model
    # ========================================================================
    ("branches", "organization_id", "organizations", "id", "CASCADE"),

    # ========================================================================
    # core.py — User model
    # ========================================================================
    ("users", "branch_id", "branches", "id", "SET NULL"),
    ("users", "organization_id", "organizations", "id", "CASCADE"),
    ("users", "manager_id", "users", "id", "SET NULL"),

    # ========================================================================
    # core.py — ApiKey model
    # ========================================================================
    ("api_keys", "user_id", "users", "id", "CASCADE"),
    ("api_keys", "organization_id", "organizations", "id", "CASCADE"),

    # ========================================================================
    # core.py — UserSettings model
    # ========================================================================
    ("user_settings", "user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # core.py — CalendarAssignment model
    # ========================================================================
    ("calendar_assignments", "organization_id", "organizations", "id", "CASCADE"),
    ("calendar_assignments", "assigned_user_id", "users", "id", "SET NULL"),

    # ========================================================================
    # core.py — EmailSignature model
    # ========================================================================
    ("email_signatures", "user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # core.py — ImpersonationSession model
    # ========================================================================
    ("impersonation_sessions", "manager_id", "users", "id", "CASCADE"),
    ("impersonation_sessions", "impersonated_user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # borrower.py — BorrowerProfile model
    # ========================================================================
    ("borrower_profiles", "organization_id", "organizations", "id", "CASCADE"),

    # ========================================================================
    # borrower.py — BorrowerApplication model
    # ========================================================================
    ("borrower_applications", "borrower_profile_id", "borrower_profiles", "id", "SET NULL"),
    ("borrower_applications", "lead_id", "leads", "id", "SET NULL"),
    ("borrower_applications", "loan_id", "loans", "id", "SET NULL"),
    ("borrower_applications", "owner_id", "users", "id", "SET NULL"),
    ("borrower_applications", "organization_id", "organizations", "id", "CASCADE"),
    ("borrower_applications", "reviewed_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # borrower.py — ApplicationDocument model
    # ========================================================================
    ("application_documents", "verified_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # compliance.py — LoanFee model
    # ========================================================================
    ("loan_fees", "organization_id", "organizations", "id", "CASCADE"),
    ("loan_fees", "loan_id", "loans", "id", "CASCADE"),

    # ========================================================================
    # compliance.py — DisclosureEvent model
    # ========================================================================
    ("disclosure_events", "organization_id", "organizations", "id", "CASCADE"),
    ("disclosure_events", "loan_id", "loans", "id", "CASCADE"),
    ("disclosure_events", "document_id", "documents", "id", "SET NULL"),
    ("disclosure_events", "created_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # compliance.py — AdverseActionNotice model
    # ========================================================================
    ("adverse_action_notices", "organization_id", "organizations", "id", "CASCADE"),
    ("adverse_action_notices", "loan_id", "loans", "id", "CASCADE"),
    ("adverse_action_notices", "lead_id", "leads", "id", "CASCADE"),
    ("adverse_action_notices", "created_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # compliance.py — ComplianceAlert model
    # ========================================================================
    ("compliance_alerts", "organization_id", "organizations", "id", "CASCADE"),
    ("compliance_alerts", "loan_id", "loans", "id", "CASCADE"),
    ("compliance_alerts", "lead_id", "leads", "id", "CASCADE"),
    ("compliance_alerts", "resolved_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # communication.py — Activity model
    # ========================================================================
    ("activities", "organization_id", "organizations", "id", "CASCADE"),
    ("activities", "lead_id", "leads", "id", "CASCADE"),
    ("activities", "loan_id", "loans", "id", "CASCADE"),
    ("activities", "mum_client_id", "mum_clients", "id", "CASCADE"),
    ("activities", "user_id", "users", "id", "SET NULL"),

    # ========================================================================
    # communication.py — StageHistory model
    # ========================================================================
    ("stage_history", "organization_id", "organizations", "id", "CASCADE"),
    ("stage_history", "lead_id", "leads", "id", "CASCADE"),
    ("stage_history", "loan_id", "loans", "id", "CASCADE"),
    ("stage_history", "changed_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # communication.py — Conversation model
    # ========================================================================
    ("conversations", "organization_id", "organizations", "id", "CASCADE"),
    ("conversations", "user_id", "users", "id", "SET NULL"),
    ("conversations", "lead_id", "leads", "id", "CASCADE"),
    ("conversations", "loan_id", "loans", "id", "CASCADE"),

    # ========================================================================
    # communication.py — ConversationMemory model
    # ========================================================================
    ("conversation_memory", "organization_id", "organizations", "id", "CASCADE"),
    ("conversation_memory", "user_id", "users", "id", "CASCADE"),
    ("conversation_memory", "lead_id", "leads", "id", "CASCADE"),
    ("conversation_memory", "loan_id", "loans", "id", "CASCADE"),

    # ========================================================================
    # communication.py — SMSMessage model
    # ========================================================================
    ("sms_messages", "organization_id", "organizations", "id", "CASCADE"),
    ("sms_messages", "user_id", "users", "id", "SET NULL"),
    ("sms_messages", "lead_id", "leads", "id", "SET NULL"),
    ("sms_messages", "loan_id", "loans", "id", "SET NULL"),
    ("sms_messages", "conversation_id", "sms_conversations", "id", "SET NULL"),

    # ========================================================================
    # communication.py — SMSConversation model
    # ========================================================================
    ("sms_conversations", "organization_id", "organizations", "id", "CASCADE"),
    ("sms_conversations", "user_id", "users", "id", "SET NULL"),
    ("sms_conversations", "lead_id", "leads", "id", "SET NULL"),
    ("sms_conversations", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — EmailMessage model
    # ========================================================================
    ("email_messages", "organization_id", "organizations", "id", "CASCADE"),
    ("email_messages", "user_id", "users", "id", "SET NULL"),
    ("email_messages", "lead_id", "leads", "id", "SET NULL"),
    ("email_messages", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — Email model
    # ========================================================================
    ("emails", "organization_id", "organizations", "id", "CASCADE"),
    ("emails", "user_id", "users", "id", "SET NULL"),
    ("emails", "lead_id", "leads", "id", "SET NULL"),

    # ========================================================================
    # communication.py — EmailDraft model
    # ========================================================================
    ("email_drafts", "organization_id", "organizations", "id", "CASCADE"),
    ("email_drafts", "user_id", "users", "id", "SET NULL"),
    ("email_drafts", "lead_id", "leads", "id", "SET NULL"),
    ("email_drafts", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — EmailVerificationToken model
    # ========================================================================
    ("email_verification_tokens", "user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # communication.py — TeamsMessage model
    # ========================================================================
    ("teams_messages", "organization_id", "organizations", "id", "CASCADE"),
    ("teams_messages", "user_id", "users", "id", "SET NULL"),
    ("teams_messages", "lead_id", "leads", "id", "SET NULL"),
    ("teams_messages", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — VoicemailDrop model
    # ========================================================================
    ("voicemail_drops", "organization_id", "organizations", "id", "CASCADE"),
    ("voicemail_drops", "lead_id", "leads", "id", "SET NULL"),
    ("voicemail_drops", "loan_id", "loans", "id", "SET NULL"),
    ("voicemail_drops", "user_id", "users", "id", "CASCADE"),
    ("voicemail_drops", "campaign_id", "voicemail_campaigns", "id", "SET NULL"),
    ("voicemail_drops", "template_id", "voicemail_templates", "id", "SET NULL"),

    # ========================================================================
    # communication.py — VoicemailTemplate model
    # ========================================================================
    ("voicemail_templates", "organization_id", "organizations", "id", "CASCADE"),
    ("voicemail_templates", "user_id", "users", "id", "SET NULL"),

    # ========================================================================
    # communication.py — VoicemailCampaign model
    # ========================================================================
    ("voicemail_campaigns", "organization_id", "organizations", "id", "CASCADE"),
    ("voicemail_campaigns", "user_id", "users", "id", "SET NULL"),
    ("voicemail_campaigns", "template_id", "voicemail_templates", "id", "SET NULL"),

    # ========================================================================
    # communication.py — VoicemailEvent model
    # ========================================================================
    ("voicemail_events", "voicemail_drop_id", "voicemail_drops", "id", "CASCADE"),

    # ========================================================================
    # communication.py — CalendarEvent model
    # ========================================================================
    ("calendar_events", "organization_id", "organizations", "id", "CASCADE"),
    ("calendar_events", "lead_id", "leads", "id", "SET NULL"),
    ("calendar_events", "loan_id", "loans", "id", "SET NULL"),
    ("calendar_events", "user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # communication.py — IntegrationLog model
    # ========================================================================
    ("integration_logs", "organization_id", "organizations", "id", "CASCADE"),
    ("integration_logs", "user_id", "users", "id", "SET NULL"),
    ("integration_logs", "lead_id", "leads", "id", "SET NULL"),
    ("integration_logs", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — IntegrationCredential model
    # ========================================================================
    ("integration_credentials", "organization_id", "organizations", "id", "CASCADE"),
    ("integration_credentials", "user_id", "users", "id", "CASCADE"),

    # ========================================================================
    # communication.py — ConversationSession model
    # ========================================================================
    ("conversation_sessions", "organization_id", "organizations", "id", "CASCADE"),
    ("conversation_sessions", "user_id", "users", "id", "CASCADE"),
    ("conversation_sessions", "lead_id", "leads", "id", "SET NULL"),
    ("conversation_sessions", "loan_id", "loans", "id", "SET NULL"),

    # ========================================================================
    # communication.py — EntityExtraction model
    # ========================================================================
    ("entity_extractions", "organization_id", "organizations", "id", "CASCADE"),
    ("entity_extractions", "session_id", "conversation_sessions", "id", "CASCADE"),
    ("entity_extractions", "conversation_memory_id", "conversation_memory", "id", "SET NULL"),

    # ========================================================================
    # communication.py — ChannelPreference model
    # ========================================================================
    ("channel_preferences", "organization_id", "organizations", "id", "CASCADE"),
    ("channel_preferences", "user_id", "users", "id", "CASCADE"),
    ("channel_preferences", "lead_id", "leads", "id", "CASCADE"),

    # ========================================================================
    # communication.py — MessageTemplate model
    # ========================================================================
    ("message_templates", "organization_id", "organizations", "id", "CASCADE"),
    ("message_templates", "created_by_id", "users", "id", "SET NULL"),

    # ========================================================================
    # audit.py — MobileAuditEvent model
    # ========================================================================
    ("mobile_audit_events", "organization_id", "organizations", "id", "CASCADE"),
    ("mobile_audit_events", "user_id", "users", "id", "CASCADE"),
]


def _find_fk_constraint_name(conn, table_name: str, column_name: str) -> str | None:
    """Find the actual FK constraint name in PostgreSQL for a given table.column."""
    from sqlalchemy import text
    result = conn.execute(
        text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = :table_name
            AND kcu.column_name = :column_name
            AND tc.table_schema = 'public'
        LIMIT 1
        """),
        {"table_name": table_name, "column_name": column_name},
    )
    row = result.fetchone()
    return row[0] if row else None


def _check_current_ondelete(conn, constraint_name: str) -> str | None:
    """Check the current ondelete action for a FK constraint."""
    from sqlalchemy import text
    result = conn.execute(
        text("""
        SELECT rc.delete_rule
        FROM information_schema.referential_constraints rc
        WHERE rc.constraint_name = :constraint_name
            AND rc.constraint_schema = 'public'
        LIMIT 1
        """),
        {"constraint_name": constraint_name},
    )
    row = result.fetchone()
    return row[0] if row else None


def run_migration():
    """Add ondelete behavior to FK constraints across all 7 priority model files."""
    from db import engine
    from sqlalchemy import text

    updated = 0
    skipped = 0
    missing_table = 0
    missing_constraint = 0
    already_correct = 0
    errors = 0

    with engine.connect() as conn:
        # Check if each table exists first
        existing_tables_result = conn.execute(
            text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """)
        )
        existing_tables = {row[0] for row in existing_tables_result.fetchall()}

        for table, column, ref_table, ref_column, ondelete in FK_UPDATES:
            if table not in existing_tables:
                logger.info(f"  SKIP {table}.{column} — table does not exist")
                missing_table += 1
                continue

            if ref_table not in existing_tables:
                logger.info(f"  SKIP {table}.{column} -> {ref_table}.{ref_column} — referenced table does not exist")
                missing_table += 1
                continue

            # Find the existing FK constraint
            constraint_name = _find_fk_constraint_name(conn, table, column)
            if not constraint_name:
                logger.info(f"  SKIP {table}.{column} — no FK constraint found (column may not exist)")
                missing_constraint += 1
                continue

            # Check current ondelete rule
            current_rule = _check_current_ondelete(conn, constraint_name)
            # PostgreSQL stores rules as: NO ACTION, CASCADE, SET NULL, SET DEFAULT, RESTRICT
            target_rule = ondelete.replace("_", " ").upper()  # "SET NULL" -> "SET NULL"

            if current_rule == target_rule:
                logger.debug(f"  OK   {table}.{column} already has ON DELETE {ondelete}")
                already_correct += 1
                continue

            # Drop and recreate the constraint
            try:
                new_constraint_name = f"fk_{table}_{column}"
                # Truncate if too long (PostgreSQL 63-char identifier limit)
                if len(new_constraint_name) > 63:
                    new_constraint_name = new_constraint_name[:63]

                conn.execute(
                    text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
                )
                conn.execute(
                    text(
                        f'ALTER TABLE "{table}" ADD CONSTRAINT "{new_constraint_name}" '
                        f'FOREIGN KEY ("{column}") REFERENCES "{ref_table}" ("{ref_column}") '
                        f"ON DELETE {ondelete}"
                    )
                )
                conn.commit()
                logger.info(
                    f"  DONE {table}.{column} -> {ref_table}.{ref_column} "
                    f"ON DELETE {ondelete} (was: {current_rule})"
                )
                updated += 1
            except Exception as e:
                logger.error(f"  ERR  {table}.{column}: {e}")
                conn.rollback()
                errors += 1

    logger.info(
        f"\nMigration complete: "
        f"{updated} updated, {already_correct} already correct, "
        f"{missing_table} missing tables, {missing_constraint} missing constraints, "
        f"{errors} errors"
    )
    return updated, errors


if __name__ == "__main__":
    logger.info("=== FK ondelete migration (Check 3.7) ===")
    updated, errors = run_migration()
    if errors:
        logger.error(f"Migration completed with {errors} errors")
        sys.exit(1)
    logger.info(f"Migration completed successfully: {updated} constraints updated")
