"""Enable Row-Level Security for tenant isolation

Revision ID: 006_rls
Revises: 005_billing
Create Date: 2026-01-31

This migration enables PostgreSQL Row-Level Security (RLS) on tenant-scoped tables.
RLS provides database-level enforcement of multi-tenant isolation by filtering
all queries based on the current tenant context set via app.current_tenant.

The tenant context should be set at the beginning of each request:
    SET app.current_tenant = '123';

Tables protected:
- leads: Lead/prospect records
- loans: Loan/application records
- ai_tasks: AI-generated tasks
- tasks: User tasks
- activities: Activity log entries
- documents: Document records
- referral_partners: Referral partner records
- mum_clients: MUM (Move-Up/Mortgage) client records
- stage_history: Stage change history

Note: sms_messages and email_messages don't have direct organization_id.
They inherit tenant context through related user/lead/loan records.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '006_rls'
down_revision = '005_billing'
branch_labels = None
depends_on = None


# Tables that have organization_id and need RLS
RLS_TABLES = [
    'leads',
    'loans',
    'ai_tasks',
    'tasks',
    'activities',
    'documents',
    'referral_partners',
    'mum_clients',
    'stage_history',
]


def upgrade():
    """Enable RLS on tenant-scoped tables."""
    bind = op.get_bind()

    # RLS only works on PostgreSQL - skip for SQLite and other databases
    if bind.dialect.name != 'postgresql':
        print("Skipping RLS migration - only supported on PostgreSQL")
        return

    for table in RLS_TABLES:
        # Check if table exists before enabling RLS
        result = bind.execute(sa.text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table}'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            print(f"Skipping RLS for '{table}' - table does not exist")
            continue

        # Check if organization_id column exists
        result = bind.execute(sa.text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table}'
                AND column_name = 'organization_id'
            )
        """))
        has_org_id = result.scalar()

        if not has_org_id:
            print(f"Skipping RLS for '{table}' - no organization_id column")
            continue

        # Enable RLS on the table
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Force RLS for table owners (superusers) as well during development
        # In production, you may want to remove this to allow admin bypass
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Create policy for tenant isolation
        # The policy uses current_setting to get the tenant from session context
        # Fail-closed: if app.current_tenant is not set, NULLIF returns NULL,
        # so organization_id = NULL is FALSE for all rows → zero rows returned
        policy_name = f"tenant_isolation_{table}"

        op.execute(f"""
            DROP POLICY IF EXISTS {policy_name} ON {table};
            CREATE POLICY {policy_name} ON {table}
            FOR ALL
            USING (
                organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
            )
            WITH CHECK (
                organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
            )
        """)

        print(f"Enabled RLS on '{table}' with policy '{policy_name}'")

    # Create a helper function to set the tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id integer)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', tenant_id::text, false);
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create a helper function to get the current tenant
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_tenant()
        RETURNS integer AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_tenant', true), '')::integer;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create a helper function to clear tenant context (for admin operations)
    op.execute("""
        CREATE OR REPLACE FUNCTION clear_tenant_context()
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', '', false);
        END;
        $$ LANGUAGE plpgsql;
    """)

    print("RLS migration complete - created helper functions")


def downgrade():
    """Disable RLS and remove policies from tenant-scoped tables."""
    bind = op.get_bind()

    # RLS only works on PostgreSQL - skip for SQLite and other databases
    if bind.dialect.name != 'postgresql':
        print("Skipping RLS downgrade - only supported on PostgreSQL")
        return

    for table in RLS_TABLES:
        # Check if table exists
        result = bind.execute(sa.text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = '{table}'
            )
        """))
        table_exists = result.scalar()

        if not table_exists:
            continue

        policy_name = f"tenant_isolation_{table}"

        # Drop the policy if it exists
        op.execute(f"""
            DROP POLICY IF EXISTS {policy_name} ON {table}
        """)

        # Disable RLS on the table
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

        print(f"Disabled RLS on '{table}'")

    # Drop helper functions
    op.execute("DROP FUNCTION IF EXISTS set_tenant_context(integer)")
    op.execute("DROP FUNCTION IF EXISTS get_current_tenant()")
    op.execute("DROP FUNCTION IF EXISTS clear_tenant_context()")

    print("RLS downgrade complete")
