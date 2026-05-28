"""Baseline stamp — marks the existing production schema as migrated.

Revision ID: 017_baseline_stamp
Revises: 016_cie
Create Date: 2026-05-27

This is a no-op migration that tells Alembic "everything up to this point
already exists in the production database."  Running `alembic stamp head`
(or the programmatic equivalent in run_alembic_migrations()) records this
revision in the alembic_version table without executing any DDL.

All prior migrations (001–016) created tables that already exist in
production via init_db.py and startup_migrations.py.  From this point
forward, new schema changes MUST go through Alembic migrations.

Why a separate stamp revision instead of just stamping 016_cie?
-  Gives a clear audit trail: "this is when we activated Alembic."
-  Future readers know that 017 is the cut-over point.
-  No risk of accidentally re-running 001–016 DDL on production.
"""

from alembic import op  # noqa: F401 — required by Alembic scaffold

revision = "017_baseline_stamp"
down_revision = "016_cie"
branch_labels = None
depends_on = None


def upgrade():
    """No-op — production schema already matches."""
    pass


def downgrade():
    """No-op — nothing to undo."""
    pass
