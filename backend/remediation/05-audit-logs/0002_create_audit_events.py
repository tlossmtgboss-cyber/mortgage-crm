"""create audit_events table

Revision ID: 0002_audit_events
Revises: 0001_baseline
Create Date: 2026-04-18

Place after the baseline revision generated in step 04.
Drop-in: backend/alembic/versions/0002_create_audit_events.py
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_audit_events"
down_revision: Union[str, None] = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgcrypto is available for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "outcome",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'success'"),
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_index("ix_audit_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_org_id", "audit_events", ["org_id"])
    op.create_index("ix_audit_resource_id", "audit_events", ["resource_id"])
    op.create_index(
        "ix_audit_actor_occurred", "audit_events", ["actor_id", "occurred_at"]
    )
    op.create_index(
        "ix_audit_resource",
        "audit_events",
        ["resource_type", "resource_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_metadata_gin",
        "audit_events",
        ["metadata"],
        postgresql_using="gin",
    )

    # Append-only guard: revoke UPDATE and DELETE at DB level.
    # App roles can only INSERT and SELECT. A separate 'audit_admin' role can
    # run retention cleanup with DELETE privileges.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'perennia_app') THEN
            REVOKE UPDATE, DELETE ON audit_events FROM perennia_app;
            GRANT INSERT, SELECT ON audit_events TO perennia_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_audit_metadata_gin", table_name="audit_events")
    op.drop_index("ix_audit_resource", table_name="audit_events")
    op.drop_index("ix_audit_actor_occurred", table_name="audit_events")
    op.drop_index("ix_audit_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_org_id", table_name="audit_events")
    op.drop_index("ix_audit_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_event_type", table_name="audit_events")
    op.drop_index("ix_audit_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
