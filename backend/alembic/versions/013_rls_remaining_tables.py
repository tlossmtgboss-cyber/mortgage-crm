"""Enable RLS on remaining tenant-scoped config tables

Revision ID: 013_rls_remaining_tables
Revises: 012_data_retention
Create Date: 2026-02-19

Domain 1 enterprise readiness: Complete RLS coverage.
Adds RLS policies to config tables that have organization_id but were
not covered by migrations 006 or 009d:
- sso_configs
- calendar_assignments
- microsoft_app_config
"""

from alembic import op
import sqlalchemy as sa

revision = '013_rls_remaining_tables'
down_revision = '012_data_retention'
branch_labels = None
depends_on = None

TABLES_TO_ADD_RLS = [
    'sso_configs',
    'calendar_assignments',
    'microsoft_app_config',
]


def _table_exists(conn, table):
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table AND table_schema = 'public'"
    ), {"table": table})
    return result.fetchone() is not None


def _column_exists(conn, table, column):
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column "
        "AND table_schema = 'public'"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    if is_sqlite:
        print("Skipping RLS migration - PostgreSQL only")
        return

    for table_name in TABLES_TO_ADD_RLS:
        if not _table_exists(conn, table_name):
            print(f"  Skipping '{table_name}' - table does not exist")
            continue

        if not _column_exists(conn, table_name, 'organization_id'):
            print(f"  Skipping '{table_name}' - no organization_id column")
            continue

        # Enable RLS
        conn.execute(sa.text(
            f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"
        ))
        conn.execute(sa.text(
            f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"
        ))

        # Create tenant isolation policy (idempotent)
        policy_name = f"tenant_isolation_{table_name}"
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"
        ))
        conn.execute(sa.text(f"""
            CREATE POLICY {policy_name} ON {table_name}
            FOR ALL
            USING (
                organization_id = NULLIF(
                    current_setting('app.current_tenant', true), ''
                )::integer
            )
            WITH CHECK (
                organization_id = NULLIF(
                    current_setting('app.current_tenant', true), ''
                )::integer
            )
        """))

        print(f"  RLS enabled on '{table_name}'")

    print("RLS remaining tables migration complete.")


def downgrade() -> None:
    conn = op.get_bind()

    if str(conn.engine.url).startswith("sqlite"):
        return

    for table_name in TABLES_TO_ADD_RLS:
        if not _table_exists(conn, table_name):
            continue

        policy_name = f"tenant_isolation_{table_name}"
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"
        ))
        conn.execute(sa.text(
            f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"
        ))
