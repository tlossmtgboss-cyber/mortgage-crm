"""Add data retention policies table

Revision ID: 012_data_retention
Revises: 011_gmi_demographics
Create Date: 2026-02-19

Enterprise Readiness Domain 8 - Check 8.9:
- Creates data_retention_policies table for per-org retention configuration
- Enables RLS on the table for tenant isolation
"""

from alembic import op
import sqlalchemy as sa

revision = '012_data_retention'
down_revision = '011_gmi_demographics'
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table AND table_schema = 'public'"
    ), {"table": table})
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    # Create data_retention_policies table
    if is_sqlite or not _table_exists(conn, "data_retention_policies"):
        op.create_table(
            "data_retention_policies",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer,
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("policy_json", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column(
                "updated_by_id",
                sa.Integer,
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )

    # Enable RLS (PostgreSQL only)
    if not is_sqlite:
        try:
            conn.execute(sa.text(
                "ALTER TABLE data_retention_policies "
                "ENABLE ROW LEVEL SECURITY"
            ))
            conn.execute(sa.text(
                "ALTER TABLE data_retention_policies "
                "FORCE ROW LEVEL SECURITY"
            ))
            conn.execute(sa.text(
                "DROP POLICY IF EXISTS tenant_isolation_data_retention_policies "
                "ON data_retention_policies"
            ))
            conn.execute(sa.text("""
                CREATE POLICY tenant_isolation_data_retention_policies
                ON data_retention_policies
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
        except Exception as e:
            print(f"RLS setup for data_retention_policies: {e}")


def downgrade() -> None:
    op.drop_table("data_retention_policies")
