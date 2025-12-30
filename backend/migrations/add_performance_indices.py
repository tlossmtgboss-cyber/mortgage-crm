"""
================================================================================
PERFORMANCE INDICES MIGRATION
================================================================================
Adds performance indices to core tables for optimal query performance.
Focuses on:
- Commonly queried columns (status, created_at, updated_at)
- Foreign key relationships
- Composite indices for common query patterns
- Partial indices for filtered queries

Supports both PostgreSQL and SQLite.
Run with: python migrations/add_performance_indices.py
================================================================================
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Fix Railway's postgres:// to postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    url = line.strip().split('=', 1)[1].strip('"').strip("'")
                    if url.startswith("postgres://"):
                        url = url.replace("postgres://", "postgresql://", 1)
                    return url

    return "sqlite:///./mortgage_crm.db"


def is_postgresql(database_url):
    """Check if database is PostgreSQL."""
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def run_migration():
    """Add performance indices to key tables."""
    from sqlalchemy import create_engine, text, inspect

    database_url = get_database_url()
    is_pg = is_postgresql(database_url)

    logger.info(f"Database: {'PostgreSQL' if is_pg else 'SQLite'}")
    logger.info(f"URL: {database_url[:50]}...")

    engine = create_engine(database_url)

    # PostgreSQL-specific indices (with partial index support)
    postgresql_indices = [
        # =====================================================================
        # CORE TABLES - Loans
        # =====================================================================
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_organization ON loans(organization_id);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_lo ON loans(loan_officer_id);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_processor ON loans(processor_id);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_created ON loans(created_at DESC);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_updated ON loans(updated_at DESC);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_status_org ON loans(organization_id, status);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_active ON loans(organization_id, status) WHERE status NOT IN ('closed', 'cancelled', 'denied');"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_close_date ON loans(target_close_date) WHERE target_close_date IS NOT NULL;"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_lock_exp ON loans(lock_expiration_date) WHERE lock_expiration_date IS NOT NULL;"),

        # =====================================================================
        # USERS
        # =====================================================================
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_active ON users(organization_id, is_active) WHERE is_active = TRUE;"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);"),

        # =====================================================================
        # CONTACTS/BORROWERS
        # =====================================================================
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization_id);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(last_name, first_name);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts(created_at DESC);"),

        # =====================================================================
        # LEADS
        # =====================================================================
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_org ON leads(organization_id);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_to);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(lead_score DESC) WHERE lead_score IS NOT NULL;"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_active ON leads(organization_id, status) WHERE status = 'active';"),

        # =====================================================================
        # TASKS
        # =====================================================================
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(assigned_to);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_loan ON tasks(loan_id);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date) WHERE due_date IS NOT NULL;"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_pending ON tasks(assigned_to, status, due_date) WHERE status = 'pending';"),

        # =====================================================================
        # DOCUMENTS
        # =====================================================================
        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_loan ON documents(loan_id);"),
        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);"),
        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);"),
        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_uploaded ON documents(uploaded_at DESC);"),

        # =====================================================================
        # NOTES
        # =====================================================================
        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_loan ON notes(loan_id);"),
        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);"),
        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at DESC);"),

        # =====================================================================
        # EMAILS
        # =====================================================================
        ("emails", "CREATE INDEX IF NOT EXISTS idx_emails_loan ON emails(loan_id);"),
        ("emails", "CREATE INDEX IF NOT EXISTS idx_emails_contact ON emails(contact_id);"),
        ("emails", "CREATE INDEX IF NOT EXISTS idx_emails_direction ON emails(direction);"),
        ("emails", "CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(email_date DESC);"),
        ("emails", "CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);"),

        # =====================================================================
        # ORGANIZATIONS
        # =====================================================================
        ("organizations", "CREATE INDEX IF NOT EXISTS idx_orgs_active ON organizations(is_active) WHERE is_active = TRUE;"),
        ("organizations", "CREATE INDEX IF NOT EXISTS idx_orgs_slug ON organizations(slug);"),

        # =====================================================================
        # PERMISSIONS AND ACCESS
        # =====================================================================
        ("user_permissions", "CREATE INDEX IF NOT EXISTS idx_user_perms_user ON user_permissions(user_id);"),
        ("role_permissions", "CREATE INDEX IF NOT EXISTS idx_role_perms_role ON role_permissions(role_id);"),
        ("audit_logs", "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);"),
        ("audit_logs", "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);"),
        ("audit_logs", "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);"),

        # =====================================================================
        # ACTIVITIES
        # =====================================================================
        ("activities", "CREATE INDEX IF NOT EXISTS idx_activities_loan ON activities(loan_id);"),
        ("activities", "CREATE INDEX IF NOT EXISTS idx_activities_user ON activities(user_id);"),
        ("activities", "CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);"),
        ("activities", "CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at DESC);"),

        # =====================================================================
        # MILESTONES/STAGES
        # =====================================================================
        ("loan_milestones", "CREATE INDEX IF NOT EXISTS idx_milestones_loan ON loan_milestones(loan_id);"),
        ("loan_milestones", "CREATE INDEX IF NOT EXISTS idx_milestones_status ON loan_milestones(status);"),
        ("stage_history", "CREATE INDEX IF NOT EXISTS idx_stage_history_loan ON stage_history(loan_id);"),
        ("stage_history", "CREATE INDEX IF NOT EXISTS idx_stage_history_date ON stage_history(changed_at DESC);"),

        # =====================================================================
        # INTEGRATIONS
        # =====================================================================
        ("integration_configs", "CREATE INDEX IF NOT EXISTS idx_integrations_org ON integration_configs(organization_id);"),
        ("integration_configs", "CREATE INDEX IF NOT EXISTS idx_integrations_type ON integration_configs(integration_type);"),
        ("sync_logs", "CREATE INDEX IF NOT EXISTS idx_sync_logs_org ON sync_logs(organization_id);"),
        ("sync_logs", "CREATE INDEX IF NOT EXISTS idx_sync_logs_status ON sync_logs(status);"),
        ("sync_logs", "CREATE INDEX IF NOT EXISTS idx_sync_logs_created ON sync_logs(created_at DESC);"),

        # =====================================================================
        # NOTIFICATIONS
        # =====================================================================
        ("notifications", "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);"),
        ("notifications", "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read_at) WHERE read_at IS NULL;"),
        ("notifications", "CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);"),

        # =====================================================================
        # REFERRAL PARTNERS
        # =====================================================================
        ("referral_partners", "CREATE INDEX IF NOT EXISTS idx_referral_partners_org ON referral_partners(organization_id);"),
        ("referral_partners", "CREATE INDEX IF NOT EXISTS idx_referral_partners_email ON referral_partners(email);"),
        ("referral_partners", "CREATE INDEX IF NOT EXISTS idx_referral_partners_type ON referral_partners(partner_type);"),

        # =====================================================================
        # CALENDAR/APPOINTMENTS
        # =====================================================================
        ("appointments", "CREATE INDEX IF NOT EXISTS idx_appointments_user ON appointments(user_id);"),
        ("appointments", "CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(start_time);"),
        ("appointments", "CREATE INDEX IF NOT EXISTS idx_appointments_loan ON appointments(loan_id);"),
        ("appointments", "CREATE INDEX IF NOT EXISTS idx_appointments_upcoming ON appointments(user_id, start_time) WHERE start_time > CURRENT_TIMESTAMP;"),

        # =====================================================================
        # WORKFLOW SLA
        # =====================================================================
        ("sla_configurations", "CREATE INDEX IF NOT EXISTS idx_sla_configs_org ON sla_configurations(organization_id);"),
        ("sla_configurations", "CREATE INDEX IF NOT EXISTS idx_sla_configs_active ON sla_configurations(organization_id, is_active) WHERE is_active = TRUE;"),
        ("sla_tracking", "CREATE INDEX IF NOT EXISTS idx_sla_tracking_loan ON sla_tracking(loan_id);"),
        ("sla_tracking", "CREATE INDEX IF NOT EXISTS idx_sla_tracking_status ON sla_tracking(status);"),
        ("sla_tracking", "CREATE INDEX IF NOT EXISTS idx_sla_tracking_due ON sla_tracking(due_at) WHERE status = 'pending';"),
    ]

    # SQLite-compatible indices (no partial indices, no WHERE clause)
    sqlite_indices = [
        # Core tables
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_organization ON loans(organization_id);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_lo ON loans(loan_officer_id);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_created ON loans(created_at);"),
        ("loans", "CREATE INDEX IF NOT EXISTS idx_loans_status_org ON loans(organization_id, status);"),

        ("users", "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);"),
        ("users", "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);"),

        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization_id);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);"),
        ("contacts", "CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(last_name, first_name);"),

        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_org ON leads(organization_id);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);"),
        ("leads", "CREATE INDEX IF NOT EXISTS idx_leads_assigned ON leads(assigned_to);"),

        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(assigned_to);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_loan ON tasks(loan_id);"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"),

        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_loan ON documents(loan_id);"),
        ("documents", "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);"),

        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_loan ON notes(loan_id);"),
        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);"),

        ("notifications", "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);"),
        ("notifications", "CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);"),
    ]

    indices = postgresql_indices if is_pg else sqlite_indices

    success_count = 0
    skip_count = 0
    error_count = 0

    with engine.connect() as conn:
        # Get existing tables
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        for table, sql in indices:
            if table not in existing_tables:
                logger.debug(f"Skipping index on {table} (table doesn't exist)")
                skip_count += 1
                continue

            try:
                conn.execute(text(sql))
                conn.commit()
                success_count += 1
                logger.info(f"✅ Created index on {table}")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.debug(f"Index already exists on {table}")
                    skip_count += 1
                else:
                    logger.warning(f"⚠️ Could not create index on {table}: {e}")
                    error_count += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"PERFORMANCE INDICES MIGRATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"✅ Created: {success_count}")
    logger.info(f"⏭️ Skipped: {skip_count}")
    logger.info(f"⚠️ Errors: {error_count}")
    logger.info(f"{'='*60}")

    return error_count == 0


if __name__ == "__main__":
    logger.info("Starting Performance Indices Migration...")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")

    success = run_migration()

    if success:
        logger.info("✅ Migration completed successfully!")
    else:
        logger.warning("⚠️ Migration completed with some errors (indices may already exist)")

    sys.exit(0 if success else 1)
