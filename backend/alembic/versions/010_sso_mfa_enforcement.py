"""Add SSO configuration table, org SSO/MFA enforcement, user SSO fields

Revision ID: 010_sso_mfa_enforcement
Revises: 009d_tenant_isolation
Create Date: 2026-02-19

Enterprise Readiness:
- Check 4.5:  SAML SSO support
- Check 4.6:  MFA enforcement (org-level mfa_required)
- Check 4.11: API key scope enforcement (expires_at already exists)
- Check 5.9:  SAML SSO configuration
- Check 5.10: OIDC provider support
- Check 5.11: JIT user provisioning (sso_provider, sso_subject_id on users)
- Check 5.12: SSO-only mode (sso_enforced on organizations)
"""

from alembic import op
import sqlalchemy as sa
import logging

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic
revision = '010_sso_mfa_enforcement'
down_revision = '009d_tenant_isolation'
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    """Check if a column exists in a table (PostgreSQL)."""
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :col"
    ), {"table": table, "col": column})
    return result.fetchone() is not None


def _table_exists(conn, table):
    """Check if a table exists (PostgreSQL)."""
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table"
    ), {"table": table})
    return result.fetchone() is not None


def upgrade():
    conn = op.get_bind()

    # Detect SQLite vs PostgreSQL
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    # ---- 1. Add sso_enforced and mfa_required to organizations ----
    if is_sqlite:
        # SQLite: just try and ignore errors
        for col, col_type in [("sso_enforced", "BOOLEAN"), ("mfa_required", "BOOLEAN")]:
            try:
                op.add_column("organizations", sa.Column(col, sa.Boolean(), server_default="false"))
            except Exception as e:
                logger.warning(f"Error adding column {col} to organizations (may already exist): {e}")
    else:
        for col in ["sso_enforced", "mfa_required"]:
            if not _column_exists(conn, "organizations", col):
                op.add_column("organizations", sa.Column(col, sa.Boolean(), server_default=sa.text("false")))

    # ---- 2. Add sso_provider and sso_subject_id to users ----
    user_cols = [
        ("sso_provider", sa.String()),
        ("sso_subject_id", sa.String()),
    ]
    if is_sqlite:
        for col_name, col_type in user_cols:
            try:
                op.add_column("users", sa.Column(col_name, col_type, nullable=True))
            except Exception as e:
                logger.warning(f"Error adding column {col_name} to users (may already exist): {e}")
    else:
        for col_name, col_type in user_cols:
            if not _column_exists(conn, "users", col_name):
                op.add_column("users", sa.Column(col_name, col_type, nullable=True))

    # ---- 3. Create sso_configs table ----
    if is_sqlite or not _table_exists(conn, "sso_configs"):
        op.create_table(
            "sso_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("provider_type", sa.String(), nullable=False, server_default="saml"),
            # SAML
            sa.Column("idp_entity_id", sa.String(), nullable=True),
            sa.Column("idp_sso_url", sa.String(), nullable=True),
            sa.Column("idp_slo_url", sa.String(), nullable=True),
            sa.Column("idp_certificate", sa.Text(), nullable=True),
            sa.Column("sp_entity_id", sa.String(), nullable=True),
            # OIDC
            sa.Column("oidc_discovery_url", sa.String(), nullable=True),
            sa.Column("oidc_client_id", sa.String(), nullable=True),
            sa.Column("oidc_client_secret", sa.Text(), nullable=True),
            sa.Column("oidc_scopes", sa.String(), server_default="openid profile email"),
            # Common
            sa.Column("default_role", sa.String(), server_default="loan_officer"),
            sa.Column("default_permission_role", sa.String(), server_default="sales"),
            sa.Column("auto_provision", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()" if not is_sqlite else "CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()" if not is_sqlite else "CURRENT_TIMESTAMP")),
        )

    # ---- 4. Enable RLS on sso_configs (PostgreSQL only) ----
    if not is_sqlite:
        try:
            conn.execute(sa.text("ALTER TABLE sso_configs ENABLE ROW LEVEL SECURITY"))
            conn.execute(sa.text("""
                DO $$ BEGIN
                    CREATE POLICY sso_configs_tenant_policy ON sso_configs
                        USING (organization_id::text = current_setting('app.current_tenant', true));
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$
            """))
        except Exception as e:
            print(f"RLS on sso_configs: {e}")


def downgrade():
    conn = op.get_bind()
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    # Drop sso_configs table
    op.drop_table("sso_configs")

    # Remove columns from users
    if not is_sqlite:
        op.drop_column("users", "sso_subject_id")
        op.drop_column("users", "sso_provider")

    # Remove columns from organizations
    if not is_sqlite:
        op.drop_column("organizations", "mfa_required")
        op.drop_column("organizations", "sso_enforced")
