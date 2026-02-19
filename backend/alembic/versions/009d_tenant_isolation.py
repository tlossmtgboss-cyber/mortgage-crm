"""Add organization_id to all tenant-scoped tables and enable RLS

Revision ID: 009d_tenant_isolation
Revises: 009c_compliance_models
Create Date: 2026-02-19

Domain 1 enterprise readiness: Multi-Tenant Isolation
- Adds organization_id column (with FK to organizations.id) to all tables
  that store per-tenant data but were missing it
- Enables Row-Level Security (RLS) on ALL tables with organization_id
- Creates RLS policies that restrict access based on app.current_tenant session var
- Idempotent: checks column/table/policy existence before each operation
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '009d_tenant_isolation'
down_revision = '009c_compliance_models'
branch_labels = None
depends_on = None


# =============================================================================
# Tables that need organization_id ADDED (they don't have it yet)
# =============================================================================
TABLES_NEEDING_ORG_ID = [
    'emails',
    'email_drafts',
    'teams_messages',
    'voicemail_templates',
    'voicemail_campaigns',
    'calendar_events',
    'integration_logs',
    'integration_credentials',
    'scheduled_workflows',
    'workflow_executions',
    'workflows',
    'ai_delegated_tasks',
    'ai_feedback_logs',
    'ai_actions',
    'ai_learning_metrics',
    'ai_audit_logs',
    'ai_colleague_actions',
    'dialer_sessions',
    'call_logs',
    'notifications',
]


# =============================================================================
# ALL tables that should have RLS (existing + newly added org_id columns)
# =============================================================================
ALL_RLS_TABLES = [
    # Already had organization_id from previous migrations
    'leads',
    'loans',
    'ai_tasks',
    'tasks',
    'activities',
    'documents',
    'referral_partners',
    'mum_clients',
    'stage_history',
    'conversations',
    'conversation_memory',
    'sms_messages',
    'sms_conversations',
    'email_messages',
    'email_intakes',
    'attachment_intakes',
    'voicemail_drops',
    'borrower_profiles',
    'borrower_applications',
    'api_keys',
    'branches',
    # Compliance models (from 009c)
    'loan_fees',
    'disclosure_events',
    'adverse_action_notices',
    'compliance_alerts',
    # Platform contracts
    'platform_contracts',
    # AI knowledge base (had org_id but no FK - migration fixes the column)
    'ai_knowledge_base',
    # Newly added in this migration
    'emails',
    'email_drafts',
    'teams_messages',
    'voicemail_templates',
    'voicemail_campaigns',
    'calendar_events',
    'integration_logs',
    'integration_credentials',
    'scheduled_workflows',
    'workflow_executions',
    'workflows',
    'ai_delegated_tasks',
    'ai_feedback_logs',
    'ai_actions',
    'ai_learning_metrics',
    'ai_audit_logs',
    'ai_colleague_actions',
    'dialer_sessions',
    'call_logs',
    'notifications',
]


# =============================================================================
# Helper functions
# =============================================================================

def _table_exists(bind, table_name):
    """Check if a table exists in the public schema."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def _column_exists(bind, table_name, column_name):
    """Check if a column exists in a table."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :table_name
            AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def _policy_exists(bind, policy_name, table_name):
    """Check if a RLS policy exists on a table."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_policies
            WHERE policyname = :policy_name
            AND tablename = :table_name
            AND schemaname = 'public'
        )
    """), {"policy_name": policy_name, "table_name": table_name})
    return result.scalar()


def _index_exists(bind, index_name):
    """Check if an index exists."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = :index_name
            AND schemaname = 'public'
        )
    """), {"index_name": index_name})
    return result.scalar()


# =============================================================================
# Upgrade
# =============================================================================

def upgrade() -> None:
    bind = op.get_bind()

    # RLS and ALTER TABLE with FK only work on PostgreSQL
    if bind.dialect.name != 'postgresql':
        print("Skipping tenant isolation migration - PostgreSQL only")
        return

    # =========================================================================
    # PHASE 1: Add organization_id columns to tables that lack them
    # =========================================================================
    print("Phase 1: Adding organization_id columns...")

    for table_name in TABLES_NEEDING_ORG_ID:
        if not _table_exists(bind, table_name):
            print(f"  Skipping '{table_name}' - table does not exist")
            continue

        if _column_exists(bind, table_name, 'organization_id'):
            print(f"  Skipping '{table_name}' - organization_id already exists")
            continue

        # Add the column (nullable to avoid breaking existing rows)
        bind.execute(sa.text(f"""
            ALTER TABLE {table_name}
            ADD COLUMN organization_id INTEGER REFERENCES organizations(id)
        """))

        # Add index for performance
        idx_name = f"ix_{table_name}_organization_id"
        if not _index_exists(bind, idx_name):
            bind.execute(sa.text(f"""
                CREATE INDEX {idx_name} ON {table_name} (organization_id)
            """))

        print(f"  Added organization_id to '{table_name}'")

    # =========================================================================
    # PHASE 1b: Fix ai_knowledge_base - has org_id but no FK constraint
    # =========================================================================
    if _table_exists(bind, 'ai_knowledge_base') and _column_exists(bind, 'ai_knowledge_base', 'organization_id'):
        # Check if FK already exists
        fk_check = bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = 'ai_knowledge_base'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND ccu.table_name = 'organizations'
                AND ccu.column_name = 'id'
            )
        """))
        if not fk_check.scalar():
            try:
                bind.execute(sa.text("""
                    ALTER TABLE ai_knowledge_base
                    ADD CONSTRAINT fk_ai_kb_org_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                """))
                print("  Added FK constraint to ai_knowledge_base.organization_id")
            except Exception as e:
                print(f"  Warning: Could not add FK to ai_knowledge_base: {e}")

        # Add index if missing
        idx_name = "ix_ai_knowledge_base_organization_id"
        if not _index_exists(bind, idx_name):
            bind.execute(sa.text(f"""
                CREATE INDEX {idx_name} ON ai_knowledge_base (organization_id)
            """))
            print("  Added index on ai_knowledge_base.organization_id")

    # =========================================================================
    # PHASE 2: Backfill organization_id from related user records
    # =========================================================================
    print("\nPhase 2: Backfilling organization_id from user records...")

    # Tables that have a user_id column - backfill org_id from users table
    user_linked_tables = {
        'emails': 'user_id',
        'email_drafts': 'user_id',
        'teams_messages': 'user_id',
        'voicemail_templates': 'user_id',
        'voicemail_campaigns': 'user_id',
        'calendar_events': 'user_id',
        'integration_logs': 'user_id',
        'integration_credentials': 'user_id',
        'scheduled_workflows': 'user_id',
        'workflow_executions': 'user_id',
        'workflows': 'user_id',
        'ai_delegated_tasks': 'user_id',
        'ai_feedback_logs': 'user_id',
        'ai_actions': 'user_id',
        'ai_learning_metrics': 'user_id',
        'ai_audit_logs': 'user_id',
        'ai_colleague_actions': 'user_id',
        'dialer_sessions': 'agent_id',
        'call_logs': 'agent_id',
        'notifications': 'user_id',
    }

    for table_name, user_col in user_linked_tables.items():
        if not _table_exists(bind, table_name):
            continue
        if not _column_exists(bind, table_name, 'organization_id'):
            continue

        try:
            result = bind.execute(sa.text(f"""
                UPDATE {table_name} t
                SET organization_id = u.organization_id
                FROM users u
                WHERE t.{user_col} = u.id
                AND t.organization_id IS NULL
                AND u.organization_id IS NOT NULL
            """))
            if result.rowcount > 0:
                print(f"  Backfilled {result.rowcount} rows in '{table_name}'")
        except Exception as e:
            print(f"  Warning: Backfill failed for '{table_name}': {e}")

    # =========================================================================
    # PHASE 3: Enable RLS on ALL tables with organization_id
    # =========================================================================
    print("\nPhase 3: Enabling Row-Level Security...")

    # Deduplicate the list
    rls_tables = list(dict.fromkeys(ALL_RLS_TABLES))

    for table_name in rls_tables:
        if not _table_exists(bind, table_name):
            print(f"  Skipping RLS for '{table_name}' - table does not exist")
            continue

        if not _column_exists(bind, table_name, 'organization_id'):
            print(f"  Skipping RLS for '{table_name}' - no organization_id column")
            continue

        # Enable RLS on the table
        bind.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
        bind.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))

        # Create policy (idempotent - drop first if exists)
        policy_name = f"tenant_isolation_{table_name}"

        bind.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))

        bind.execute(sa.text(f"""
            CREATE POLICY {policy_name} ON {table_name}
            FOR ALL
            USING (
                organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
            )
            WITH CHECK (
                organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
            )
        """))

        print(f"  RLS enabled on '{table_name}' with policy '{policy_name}'")

    # =========================================================================
    # PHASE 4: Ensure helper functions exist (may have been created by 006)
    # =========================================================================
    print("\nPhase 4: Ensuring RLS helper functions...")

    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id integer)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', tenant_id::text, false);
        END;
        $$ LANGUAGE plpgsql;
    """))

    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION get_current_tenant()
        RETURNS integer AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_tenant', true), '')::integer;
        END;
        $$ LANGUAGE plpgsql;
    """))

    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION clear_tenant_context()
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', '', false);
        END;
        $$ LANGUAGE plpgsql;
    """))

    print("\nTenant isolation migration complete.")


# =============================================================================
# Downgrade
# =============================================================================

def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != 'postgresql':
        print("Skipping tenant isolation downgrade - PostgreSQL only")
        return

    # Deduplicate
    rls_tables = list(dict.fromkeys(ALL_RLS_TABLES))

    # Disable RLS and drop policies
    for table_name in rls_tables:
        if not _table_exists(bind, table_name):
            continue

        policy_name = f"tenant_isolation_{table_name}"
        bind.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
        bind.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    # Drop organization_id columns from tables we added them to
    for table_name in TABLES_NEEDING_ORG_ID:
        if not _table_exists(bind, table_name):
            continue
        if not _column_exists(bind, table_name, 'organization_id'):
            continue

        idx_name = f"ix_{table_name}_organization_id"
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {idx_name}"))
        bind.execute(sa.text(f"ALTER TABLE {table_name} DROP COLUMN organization_id"))

    # Drop FK on ai_knowledge_base (but keep the column - it existed before)
    if _table_exists(bind, 'ai_knowledge_base'):
        bind.execute(sa.text("""
            ALTER TABLE ai_knowledge_base
            DROP CONSTRAINT IF EXISTS fk_ai_kb_org_id
        """))

    print("Tenant isolation downgrade complete.")
