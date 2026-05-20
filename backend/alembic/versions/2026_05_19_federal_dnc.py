"""Federal DNC registry local mirror table (D4 CC-004 closeout).

Creates ``federal_dnc_numbers`` — the local mirror of the FTC's federal
Do-Not-Call registry that ``FederalDNCSyncService`` populates on its
daily 02:00 UTC cron and that ``ComplianceChecker.check_dnc`` consults
before allowing a dial.

Schema:
    phone_number  VARCHAR(20)  PK   — NNN-NNN-NNNN normalized
    added_at      TIMESTAMP         — when first imported
    source        VARCHAR(50)       — defaults to 'federal_registry'
    is_active     BOOLEAN           — soft-delete flag for opt-back-in flow

Dialect-aware: works on PostgreSQL (production) and SQLite (test).

Revision ID: 2026_05_19_federal_dnc
Revises: 2026_05_19_audit_immutability
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "2026_05_19_federal_dnc"
down_revision = "2026_05_19_audit_immutability"
branch_labels = None
depends_on = None


TABLE_NAME = "federal_dnc_numbers"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME in inspector.get_table_names():
        return  # idempotent — table already present

    op.create_table(
        TABLE_NAME,
        sa.Column("phone_number", sa.String(length=20), primary_key=True, nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="federal_registry",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # Helpful supporting index (separate from PK) for active-filter scans.
    op.create_index(
        "ix_federal_dnc_numbers_active",
        TABLE_NAME,
        ["is_active"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        return
    try:
        op.drop_index("ix_federal_dnc_numbers_active", table_name=TABLE_NAME)
    except Exception:
        pass
    op.drop_table(TABLE_NAME)
