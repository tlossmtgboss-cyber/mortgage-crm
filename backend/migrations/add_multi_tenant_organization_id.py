"""
Multi-Tenant Organization ID Migration
======================================
Adds organization_id column to all core tables for proper tenant isolation.

This is CRITICAL for supporting 1000+ separate companies with isolated data.

Tables being updated:
- leads (via owner.organization_id)
- loans (via loan_officer.organization_id)
- tasks (via owner.organization_id)
- ai_tasks (via assigned_to.organization_id)
- activities (via user.organization_id)
- documents (via borrower.owner.organization_id or loan.loan_officer.organization_id)
- referral_partners (via owner.organization_id)
- mum_clients (via user.organization_id)
- stage_history (via lead/loan organization)
- conversations (via user.organization_id)
- email_intakes (via processed_by_user.organization_id)
- voicemail_drops (via user.organization_id)

Run with: python -m migrations.add_multi_tenant_organization_id
"""
import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Add organization_id to all core tables for multi-tenancy."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    # Fix postgres:// to postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    # Detect database type
    is_sqlite = "sqlite" in database_url.lower()
    is_postgres = "postgresql" in database_url.lower()

    with engine.connect() as conn:
        try:
            # ================================================================
            # STEP 1: Add organization_id column to all core tables
            # ================================================================
            tables_to_update = [
                'leads',
                'loans',
                'tasks',
                'ai_tasks',
                'activities',
                'documents',
                'referral_partners',
                'mum_clients',
                'stage_history',
                'conversations',
                'email_intakes',
                'attachment_intakes',
                'voicemail_drops',
                'voicemail_templates',
                'voicemail_campaigns',
                'loan_team_members',
                'ai_delegated_tasks',
                'ai_feedback_logs',
            ]

            for table in tables_to_update:
                try:
                    # Check if column already exists
                    if is_postgres:
                        result = conn.execute(text("""
                            SELECT column_name FROM information_schema.columns
                            WHERE table_name = :table_name AND column_name = 'organization_id'
                        """), {"table_name": table})
                    else:
                        result = conn.execute(text(f"PRAGMA table_info({table})"))
                        columns = [row[1] for row in result.fetchall()]
                        result = iter([{'column_name': 'organization_id'}] if 'organization_id' in columns else [])

                    if is_postgres:
                        existing = result.fetchone()
                    else:
                        existing = next(result, None)

                    if existing:
                        logger.info(f"Column organization_id already exists in {table}, skipping")
                        continue

                    # Add the column
                    if is_postgres:
                        conn.execute(text(f"""
                            ALTER TABLE {table}
                            ADD COLUMN organization_id INTEGER REFERENCES organizations(id)
                        """))
                    else:
                        conn.execute(text(f"""
                            ALTER TABLE {table} ADD COLUMN organization_id INTEGER
                        """))

                    logger.info(f"Added organization_id column to {table}")

                except Exception as e:
                    # Table might not exist, skip it
                    logger.warning(f"Could not add organization_id to {table}: {e}")
                    continue

            conn.commit()

            # ================================================================
            # STEP 2: Create indexes for organization_id queries
            # ================================================================
            index_statements = [
                "CREATE INDEX IF NOT EXISTS ix_leads_organization_id ON leads(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_loans_organization_id ON loans(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_tasks_organization_id ON tasks(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_ai_tasks_organization_id ON ai_tasks(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_activities_organization_id ON activities(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_documents_organization_id ON documents(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_referral_partners_organization_id ON referral_partners(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_mum_clients_organization_id ON mum_clients(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_stage_history_organization_id ON stage_history(organization_id)",
                "CREATE INDEX IF NOT EXISTS ix_conversations_organization_id ON conversations(organization_id)",
                # Composite indexes for common queries
                "CREATE INDEX IF NOT EXISTS ix_leads_org_stage ON leads(organization_id, stage)",
                "CREATE INDEX IF NOT EXISTS ix_leads_org_owner ON leads(organization_id, owner_id)",
                "CREATE INDEX IF NOT EXISTS ix_loans_org_stage ON loans(organization_id, stage)",
                "CREATE INDEX IF NOT EXISTS ix_loans_org_officer ON loans(organization_id, loan_officer_id)",
                "CREATE INDEX IF NOT EXISTS ix_tasks_org_status ON tasks(organization_id, status)",
                "CREATE INDEX IF NOT EXISTS ix_activities_org_created ON activities(organization_id, created_at)",
            ]

            for stmt in index_statements:
                try:
                    conn.execute(text(stmt))
                    logger.info(f"Created index: {stmt.split(' ON ')[0].split()[-1]}")
                except Exception as e:
                    logger.warning(f"Index creation skipped: {e}")

            conn.commit()

            # ================================================================
            # STEP 3: Backfill organization_id from owner/user relationships
            # ================================================================
            backfill_statements = []

            if is_postgres:
                # PostgreSQL backfill statements with proper UPDATE...FROM syntax
                backfill_statements = [
                    # Leads: get organization from owner
                    """
                    UPDATE leads
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE leads.owner_id = u.id
                    AND leads.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # Loans: get organization from loan officer
                    """
                    UPDATE loans
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE loans.loan_officer_id = u.id
                    AND loans.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # Tasks: get organization from owner
                    """
                    UPDATE tasks
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE tasks.owner_id = u.id
                    AND tasks.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # AI Tasks: get organization from assigned_to
                    """
                    UPDATE ai_tasks
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE ai_tasks.assigned_to_id = u.id
                    AND ai_tasks.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # Activities: get organization from user
                    """
                    UPDATE activities
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE activities.user_id = u.id
                    AND activities.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # Documents: get organization from borrower's owner or loan's officer
                    """
                    UPDATE documents
                    SET organization_id = COALESCE(
                        (SELECT u.organization_id FROM leads l JOIN users u ON l.owner_id = u.id WHERE l.id = documents.borrower_id),
                        (SELECT u.organization_id FROM loans lo JOIN users u ON lo.loan_officer_id = u.id WHERE lo.id = documents.loan_id)
                    )
                    WHERE documents.organization_id IS NULL
                    """,
                    # Referral partners: get organization from owner
                    """
                    UPDATE referral_partners
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE referral_partners.owner_id = u.id
                    AND referral_partners.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # MUM clients: get organization from user
                    """
                    UPDATE mum_clients
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE mum_clients.user_id = u.id
                    AND mum_clients.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                    # Stage history: get organization from lead or loan
                    """
                    UPDATE stage_history
                    SET organization_id = COALESCE(
                        (SELECT l.organization_id FROM leads l WHERE l.id = stage_history.lead_id),
                        (SELECT lo.organization_id FROM loans lo WHERE lo.id = stage_history.loan_id)
                    )
                    WHERE stage_history.organization_id IS NULL
                    """,
                    # Conversations: get organization from user
                    """
                    UPDATE conversations
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE conversations.user_id = u.id
                    AND conversations.organization_id IS NULL
                    AND u.organization_id IS NOT NULL
                    """,
                ]
            else:
                # SQLite backfill statements (subquery style)
                backfill_statements = [
                    """
                    UPDATE leads
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = leads.owner_id
                    )
                    WHERE organization_id IS NULL AND owner_id IS NOT NULL
                    """,
                    """
                    UPDATE loans
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = loans.loan_officer_id
                    )
                    WHERE organization_id IS NULL AND loan_officer_id IS NOT NULL
                    """,
                    """
                    UPDATE tasks
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = tasks.owner_id
                    )
                    WHERE organization_id IS NULL AND owner_id IS NOT NULL
                    """,
                    """
                    UPDATE activities
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = activities.user_id
                    )
                    WHERE organization_id IS NULL AND user_id IS NOT NULL
                    """,
                    """
                    UPDATE referral_partners
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = referral_partners.owner_id
                    )
                    WHERE organization_id IS NULL AND owner_id IS NOT NULL
                    """,
                    """
                    UPDATE mum_clients
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = mum_clients.user_id
                    )
                    WHERE organization_id IS NULL AND user_id IS NOT NULL
                    """,
                    """
                    UPDATE conversations
                    SET organization_id = (
                        SELECT u.organization_id FROM users u WHERE u.id = conversations.user_id
                    )
                    WHERE organization_id IS NULL AND user_id IS NOT NULL
                    """,
                ]

            for stmt in backfill_statements:
                try:
                    result = conn.execute(text(stmt))
                    logger.info(f"Backfilled organization_id: {result.rowcount} rows updated")
                except Exception as e:
                    logger.warning(f"Backfill skipped: {e}")

            conn.commit()
            logger.info("Multi-tenant organization_id migration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            conn.rollback()
            return False


def verify_migration():
    """Verify the migration was successful."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check leads table
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(organization_id) as with_org,
                COUNT(*) - COUNT(organization_id) as without_org
            FROM leads
        """))
        row = result.fetchone()
        print(f"Leads: {row[0]} total, {row[1]} with org_id, {row[2]} without org_id")

        # Check loans table
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(organization_id) as with_org,
                COUNT(*) - COUNT(organization_id) as without_org
            FROM loans
        """))
        row = result.fetchone()
        print(f"Loans: {row[0]} total, {row[1]} with org_id, {row[2]} without org_id")

        # Check tasks table
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(organization_id) as with_org,
                COUNT(*) - COUNT(organization_id) as without_org
            FROM tasks
        """))
        row = result.fetchone()
        print(f"Tasks: {row[0]} total, {row[1]} with org_id, {row[2]} without org_id")

        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("\n=== Verification ===")
        verify_migration()
    exit(0 if success else 1)
