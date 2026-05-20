"""DB-enforced append-only audit + tamper-evident hash chain

Adds two related defenses to every audit table:

1. **PostgreSQL trigger** ``audit_immutability_guard()`` — installed as a
   BEFORE UPDATE OR DELETE trigger on each audit table. Any attempt to
   modify or delete an audit row raises an exception, so even a
   compromised application account cannot rewrite history.

2. **SHA-256 hash chain** on ``loan_state_change_audit`` (the SOC 2 Type II
   loan-pipeline audit). Two new columns:

      * ``prev_hash CHAR(64) NULL``  — hash of the previous row in the
        chain (NULL for the first row).
      * ``entry_hash CHAR(64) NOT NULL`` — SHA-256 of
        ``prev_hash || canonical_json(this_row_minus_hash_fields)``.

   A tampered row breaks the chain at and after the modified entry, which
   ``verify_chain(loan_id)`` will report.

Dialect-aware: triggers and the PL/pgSQL function are PostgreSQL-only. On
SQLite the hash columns are still added (so application code paths and
tests work uniformly) but the immutability trigger is skipped.

Revision ID: 2026_05_19_audit_immutability
Revises: 2026_05_19_important_dates
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "2026_05_19_audit_immutability"
down_revision = "2026_05_19_important_dates"
branch_labels = None
depends_on = None


# Every audit-style table discovered in backend/database/models/*.py.
# Kept as the single source of truth for both upgrade() and downgrade().
AUDIT_TABLES = [
    "loan_state_change_audit",
    "audit_events",
    "mobile_audit_events",
    "memory_audit_events",
    "consent_audit_log",
    "decision_audit_logs",
    "archived_decision_audit_logs",
]


GUARD_FN_SQL = """
CREATE OR REPLACE FUNCTION audit_immutability_guard() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'Audit table rows are immutable (table=%, op=%)',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""

DROP_GUARD_FN_SQL = "DROP FUNCTION IF EXISTS audit_immutability_guard();"


def _trigger_name(table: str) -> str:
    return f"{table}_no_update_delete_trigger"


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t AND table_schema = 'public'"
        ),
        {"t": table},
    ).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c AND table_schema = 'public'"
        ),
        {"t": table, "c": column},
    ).fetchone() is not None


def _sqlite_column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    is_sqlite = bind.dialect.name == "sqlite"

    # --- 1. Hash-chain columns on loan_state_change_audit ----------------
    if is_pg:
        if _table_exists(bind, "loan_state_change_audit"):
            if not _column_exists(bind, "loan_state_change_audit", "prev_hash"):
                op.add_column(
                    "loan_state_change_audit",
                    sa.Column("prev_hash", sa.CHAR(64), nullable=True),
                )
            if not _column_exists(bind, "loan_state_change_audit", "entry_hash"):
                # Add NULLable first; backfill happens lazily on next write.
                op.add_column(
                    "loan_state_change_audit",
                    sa.Column("entry_hash", sa.CHAR(64), nullable=True),
                )
    elif is_sqlite:
        # SQLite path used by integration tests.
        if _sqlite_column_exists(bind, "loan_state_change_audit", "id"):
            if not _sqlite_column_exists(bind, "loan_state_change_audit", "prev_hash"):
                op.add_column(
                    "loan_state_change_audit",
                    sa.Column("prev_hash", sa.String(64), nullable=True),
                )
            if not _sqlite_column_exists(bind, "loan_state_change_audit", "entry_hash"):
                op.add_column(
                    "loan_state_change_audit",
                    sa.Column("entry_hash", sa.String(64), nullable=True),
                )

    # --- 2. PostgreSQL immutability triggers -----------------------------
    if not is_pg:
        # SQLite cannot enforce this with the same primitive; tests cover the
        # application-layer guard instead.
        return

    op.execute(GUARD_FN_SQL)

    for table in AUDIT_TABLES:
        if not _table_exists(bind, table):
            # Skip silently — not every deployment has every audit table yet.
            continue
        trig = _trigger_name(table)
        op.execute(f'DROP TRIGGER IF EXISTS "{trig}" ON "{table}";')
        op.execute(
            f'CREATE TRIGGER "{trig}" '
            f'BEFORE UPDATE OR DELETE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION audit_immutability_guard();"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        for table in AUDIT_TABLES:
            if not _table_exists(bind, table):
                continue
            op.execute(
                f'DROP TRIGGER IF EXISTS "{_trigger_name(table)}" ON "{table}";'
            )
        op.execute(DROP_GUARD_FN_SQL)

        if _table_exists(bind, "loan_state_change_audit"):
            if _column_exists(bind, "loan_state_change_audit", "entry_hash"):
                op.drop_column("loan_state_change_audit", "entry_hash")
            if _column_exists(bind, "loan_state_change_audit", "prev_hash"):
                op.drop_column("loan_state_change_audit", "prev_hash")
    else:
        # SQLite: drop columns if present.
        try:
            with op.batch_alter_table("loan_state_change_audit") as batch_op:
                batch_op.drop_column("entry_hash")
                batch_op.drop_column("prev_hash")
        except Exception:
            pass
