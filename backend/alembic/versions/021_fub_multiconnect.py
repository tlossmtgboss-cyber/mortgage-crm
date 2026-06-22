"""Follow Up Boss multi-account support

Revision ID: 021_fub_multiconnect
Revises: 020_password_changed_at
Create Date: 2026-06-22

Allows multiple FUB accounts per user by:
1. Dropping the unique constraint on fub_user_connections.user_id
2. Adding account_label column for human-readable connection names
"""
import sqlalchemy as sa
from alembic import op

revision = "021_fub_multiconnect"
down_revision = "020_password_changed_at"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        try:
            op.add_column("fub_user_connections", sa.Column("account_label", sa.String(100), nullable=True))
        except Exception:
            pass
        return

    op.execute("ALTER TABLE fub_user_connections ADD COLUMN IF NOT EXISTS account_label VARCHAR(100)")
    op.execute("ALTER TABLE fub_user_connections DROP CONSTRAINT IF EXISTS fub_user_connections_user_id_key")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute(
        "ALTER TABLE fub_user_connections ADD CONSTRAINT fub_user_connections_user_id_key UNIQUE (user_id)"
    )
    op.drop_column("fub_user_connections", "account_label")
