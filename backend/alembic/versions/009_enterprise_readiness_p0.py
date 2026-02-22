"""Enterprise readiness P0: multi-tenant isolation for 7 models + RLS

Revision ID: 009_enterprise_readiness_p0
Revises: 008_call_intelligence_orchestration
Create Date: 2026-02-19

This migration adds organization_id columns and Row-Level Security policies
to 7 tables that were missing multi-tenant isolation:

Communication models:
  - conversation_memory
  - sms_messages
  - sms_conversations
  - email_messages

Borrower models:
  - borrower_profiles

Document models:
  - email_intakes
  - attachment_intakes

All columns are nullable to support existing data that predates multi-tenancy.
RLS policies use the same fail-closed pattern as 006_enable_row_level_security.py.
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic
revision = '009_enterprise_readiness_p0'
down_revision = '008_call_intelligence_orchestration'
branch_labels = None
depends_on = None

# Tables to add organization_id and RLS
NEW_TENANT_TABLES = [
    'conversation_memory',
    'sms_messages',
    'sms_conversations',
    'email_messages',
    'borrower_profiles',
    'email_intakes',
    'attachment_intakes',
]

# Index names for each table
INDEX_NAMES = {
    'conversation_memory': 'ix_conversation_memory_organization_id',
    'sms_messages': 'ix_sms_messages_organization_id',
    'sms_conversations': 'ix_sms_conversations_organization_id',
    'email_messages': 'ix_email_messages_organization_id',
    'borrower_profiles': 'ix_borrower_profile_org_id',
    'email_intakes': 'ix_email_intakes_organization_id',
    'attachment_intakes': 'ix_attachment_intakes_organization_id',
}


def upgrade():
    """Add organization_id to 7 tables and enable RLS."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    for table in NEW_TENANT_TABLES:
        # Check if table exists
        if is_postgres:
            result = bind.execute(sa.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
            """), {"table_name": table})
            table_exists = result.scalar()
        else:
            # SQLite: check sqlite_master
            result = bind.execute(sa.text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:table_name"
            ), {"table_name": table})
            table_exists = result.scalar() > 0

        if not table_exists:
            print(f"Skipping '{table}' - table does not exist")
            continue

        # Check if organization_id column already exists
        if is_postgres:
            result = bind.execute(sa.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                    AND column_name = 'organization_id'
                )
            """), {"table_name": table})
            has_org_id = result.scalar()
        else:
            result = bind.execute(sa.text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result.fetchall()]
            has_org_id = 'organization_id' in columns

        if has_org_id:
            print(f"Skipping '{table}' - organization_id column already exists")
        else:
            # Add organization_id column (nullable for existing data)
            op.add_column(
                table,
                sa.Column('organization_id', sa.Integer(),
                          sa.ForeignKey('organizations.id'), nullable=True)
            )
            print(f"Added organization_id column to '{table}'")

        # Create index (skip if already exists)
        index_name = INDEX_NAMES.get(table, f'ix_{table}_organization_id')
        try:
            op.create_index(index_name, table, ['organization_id'])
            print(f"Created index '{index_name}' on '{table}'")
        except Exception as e:
            print(f"Index '{index_name}' on '{table}' may already exist: {e}")

    # =========================================================================
    # Enable RLS on the new tables (PostgreSQL only)
    # =========================================================================
    if not is_postgres:
        print("Skipping RLS - only supported on PostgreSQL")
        return

    for table in NEW_TENANT_TABLES:
        # Verify table exists and has organization_id
        result = bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = :table_name
                AND column_name = 'organization_id'
            )
        """), {"table_name": table})
        if not result.scalar():
            print(f"Skipping RLS for '{table}' - no organization_id column")
            continue

        # Enable RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Create tenant isolation policy (fail-closed pattern)
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

    print("Enterprise readiness P0 migration complete")


def downgrade():
    """Remove RLS and organization_id from the 7 tables."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    # Disable RLS first (PostgreSQL only)
    if is_postgres:
        for table in NEW_TENANT_TABLES:
            result = bind.execute(sa.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
            """), {"table_name": table})
            if not result.scalar():
                continue

            policy_name = f"tenant_isolation_{table}"
            op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
            print(f"Disabled RLS on '{table}'")

    # Remove indexes and columns
    for table in NEW_TENANT_TABLES:
        # Check if table exists
        if is_postgres:
            result = bind.execute(sa.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
            """), {"table_name": table})
            table_exists = result.scalar()
        else:
            result = bind.execute(sa.text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:table_name"
            ), {"table_name": table})
            table_exists = result.scalar() > 0

        if not table_exists:
            continue

        index_name = INDEX_NAMES.get(table, f'ix_{table}_organization_id')
        try:
            op.drop_index(index_name, table_name=table)
        except Exception as e:
            logger.error(f"Error dropping index {index_name}: {e}")

        try:
            op.drop_column(table, 'organization_id')
            print(f"Removed organization_id from '{table}'")
        except Exception as e:
            print(f"Could not remove organization_id from '{table}': {e}")

    print("Enterprise readiness P0 downgrade complete")
