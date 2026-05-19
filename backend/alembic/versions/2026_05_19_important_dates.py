"""Important Dates consolidated model — add missing milestone columns.

Adds canonical milestone date columns (new_lead_date, application_date,
disclosed_date, processing_date, submitted_date, uw_submission_date,
conditional_approval_date, approved_date, ctc_date, clear_to_close_date,
docs_out_date, closing_date, funded_date) to the ``loans`` and ``leads``
tables when they are not already present.

Dialect-aware: uses information_schema on PostgreSQL and PRAGMA on SQLite.
Idempotent: skips columns that already exist (legacy pre-consolidation
fields are preserved).

Revision ID: 2026_05_19_important_dates
Revises: 2026_05_19_float_to_numeric
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2026_05_19_important_dates"
down_revision = "2026_05_19_float_to_numeric"
branch_labels = None
depends_on = None


# Canonical milestone columns (name, indexed)
IMPORTANT_DATE_COLUMNS = [
    ("new_lead_date", True),
    ("application_date", True),
    ("disclosed_date", True),
    ("processing_date", True),
    ("submitted_date", True),
    ("uw_submission_date", True),
    ("conditional_approval_date", True),
    ("approved_date", True),
    ("ctc_date", True),
    ("clear_to_close_date", True),
    ("docs_out_date", True),
    ("closing_date", True),
    ("funded_date", True),
]

TARGET_TABLES = ["loans", "leads"]


def _existing_columns(conn, table_name: str) -> set:
    dialect = conn.dialect.name
    try:
        if dialect == "postgresql":
            rows = conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": table_name},
            ).fetchall()
            return {r[0] for r in rows}
        if dialect == "sqlite":
            rows = conn.execute(
                sa.text(f"PRAGMA table_info('{table_name}')")
            ).fetchall()
            return {r[1] for r in rows}
        # Fallback: SQLAlchemy inspector
        from sqlalchemy import inspect
        return {c["name"] for c in inspect(conn).get_columns(table_name)}
    except Exception:
        return set()


def _table_exists(conn, table_name: str) -> bool:
    dialect = conn.dialect.name
    try:
        if dialect == "postgresql":
            row = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :t"
                ),
                {"t": table_name},
            ).first()
            return row is not None
        if dialect == "sqlite":
            row = conn.execute(
                sa.text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name=:t"
                ),
                {"t": table_name},
            ).first()
            return row is not None
        from sqlalchemy import inspect
        return table_name in inspect(conn).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    use_tz = dialect == "postgresql"

    for table in TARGET_TABLES:
        if not _table_exists(conn, table):
            continue
        existing = _existing_columns(conn, table)
        for col_name, indexed in IMPORTANT_DATE_COLUMNS:
            if col_name in existing:
                continue
            with op.batch_alter_table(table) as batch:
                batch.add_column(
                    sa.Column(
                        col_name,
                        sa.DateTime(timezone=use_tz),
                        nullable=True,
                    )
                )
            if indexed:
                try:
                    op.create_index(
                        f"ix_{table}_{col_name}",
                        table,
                        [col_name],
                        unique=False,
                    )
                except Exception:
                    # Index may already exist on legacy columns; ignore.
                    pass


def downgrade() -> None:
    # Non-destructive: only drop columns we know were added by this migration.
    # We cannot reliably detect which columns this migration added vs. those
    # that pre-existed, so downgrade is intentionally a no-op to preserve
    # any milestone data captured during the consolidation window.
    pass
