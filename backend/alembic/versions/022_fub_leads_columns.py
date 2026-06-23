"""Add FUB sync columns to leads table

Revision ID: 022_fub_leads_columns
Revises: 021_fub_multiconnect
Create Date: 2026-06-22

Adds two columns needed for Follow Up Boss person sync:
  leads.fub_person_id      — FUB person ID for bidirectional lookup
  leads.fub_last_synced_at — timestamp of last FUB sync for this lead
"""
import sqlalchemy as sa
from alembic import op

revision = "022_fub_leads_columns"
down_revision = "021_fub_multiconnect"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        try:
            op.add_column("leads", sa.Column("fub_person_id", sa.Integer(), nullable=True))
        except Exception:
            pass
        try:
            op.add_column("leads", sa.Column("fub_last_synced_at", sa.DateTime(), nullable=True))
        except Exception:
            pass
        return

    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS fub_person_id INTEGER")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS fub_last_synced_at TIMESTAMP")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS fub_person_id")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS fub_last_synced_at")
