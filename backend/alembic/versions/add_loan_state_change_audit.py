"""Add loan_state_change_audit table (D5 — SOC 2 durable audit trail)

Revision ID: 2026_05_19_audit_table
Revises: 015_inline_ddl_consolidation
Create Date: 2026-05-19

Creates the `loan_state_change_audit` table — an INSERT-ONLY audit log of
every loan/lead pipeline-stage transition (manual, salesforce_sync,
reconciliation, webhook, etc.). Required for SOC 2 Type II compliance.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "2026_05_19_audit_table"
down_revision = "015_inline_ddl_consolidation"
branch_labels = None
depends_on = None


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table AND table_schema = 'public'"
    ), {"table": table})
    return result.fetchone() is not None


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    if not _table_exists(conn, "loan_state_change_audit"):
        op.create_table(
            "loan_state_change_audit",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True) if not is_sqlite else sa.String(36),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()") if not is_sqlite else None,
            ),
            sa.Column(
                "loan_id",
                sa.Integer(),
                sa.ForeignKey("loans.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "lead_id",
                postgresql.UUID(as_uuid=True) if not is_sqlite else sa.String(36),
                nullable=True,
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True) if not is_sqlite else sa.String(36),
                nullable=False,
            ),
            sa.Column("from_stage", sa.String(64), nullable=True),
            sa.Column("to_stage", sa.String(64), nullable=False),
            sa.Column("from_pipeline", sa.String(32), nullable=True),
            sa.Column("to_pipeline", sa.String(32), nullable=False),
            sa.Column("trigger_source", sa.String(64), nullable=False),
            sa.Column(
                "actor_user_id",
                postgresql.UUID(as_uuid=True) if not is_sqlite else sa.String(36),
                nullable=True,
            ),
            sa.Column(
                "audit_metadata",
                postgresql.JSONB() if not is_sqlite else sa.JSON(),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # Single-column indexes
    for col in ("loan_id", "lead_id", "organization_id", "created_at"):
        idx_name = f"ix_loan_state_change_audit_{col}"
        if not _index_exists(conn, idx_name):
            op.create_index(idx_name, "loan_state_change_audit", [col])

    # Composite index for the most common query pattern
    composite_idx = "ix_loan_state_audit_org_loan_created"
    if not _index_exists(conn, composite_idx):
        op.create_index(
            composite_idx,
            "loan_state_change_audit",
            ["organization_id", "loan_id", "created_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    for idx in (
        "ix_loan_state_audit_org_loan_created",
        "ix_loan_state_change_audit_created_at",
        "ix_loan_state_change_audit_organization_id",
        "ix_loan_state_change_audit_lead_id",
        "ix_loan_state_change_audit_loan_id",
    ):
        if _index_exists(conn, idx):
            op.drop_index(idx, table_name="loan_state_change_audit")

    if _table_exists(conn, "loan_state_change_audit"):
        op.drop_table("loan_state_change_audit")
