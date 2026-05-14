"""Consolidate inline DDL from start.py into Alembic

Revision ID: 015_inline_ddl_consolidation
Revises: 014_client_file_and_team_chat
Create Date: 2026-05-14

Moves all remaining inline CREATE TABLE IF NOT EXISTS statements from
start.py::_ensure_new_tables() into proper Alembic management.

Tables created here (that were NOT in migration 014):
  audit_events      — Compliance audit trail
  ai_cost_records   — Per-request LLM cost tracking

Tables already handled by migration 014 (re-checked idempotently):
  client_files, client_file_collaborators,
  team_chat_channels, team_chat_messages,
  team_chat_reactions, team_chat_reads,
  and 3 enum types (team_chat_author_kind, team_chat_agent_slug,
                     team_chat_reaction_emoji)

All operations use IF NOT EXISTS / DO $$ ... EXCEPTION WHEN ... $$
so this migration is safe to run against databases where start.py
already created these objects.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015_inline_ddl_consolidation"
down_revision = "014_client_file_and_team_chat"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table AND table_schema = 'public'"
    ), {"table": table})
    return result.fetchone() is not None


def _type_exists(conn, type_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = :name"
    ), {"name": type_name})
    return result.fetchone() is not None


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    conn = op.get_bind()
    is_sqlite = str(conn.engine.url).startswith("sqlite")

    if is_sqlite:
        print("015: Skipping — PostgreSQL only")
        return

    # ------------------------------------------------------------------
    # 1. Ensure enum types exist (migration 014 creates these, but
    #    start.py may have beaten it on a stamped database).
    # ------------------------------------------------------------------
    for type_name, values in [
        ("team_chat_author_kind", "'human', 'system'"),
        ("team_chat_agent_slug",
         "'cadence', 'aria', 'avery', 'insight', "
         "'ops_manager', 'document', 'milestone', 'lifecycle'"),
        ("team_chat_reaction_emoji",
         "'thumbs_up', 'check', 'fire', 'question'"),
    ]:
        if not _type_exists(conn, type_name):
            op.execute(f"CREATE TYPE {type_name} AS ENUM ({values})")
            print(f"  Created enum type {type_name}")
        else:
            print(f"  Enum type {type_name} already exists — skipping")

    # ------------------------------------------------------------------
    # 2. client_files  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "client_files"):
        op.create_table(
            "client_files",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(),
                      sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("lead_id", sa.Integer(),
                      sa.ForeignKey("leads.id"), nullable=True, unique=True),
            sa.Column("first_name", sa.String(), nullable=True),
            sa.Column("last_name", sa.String(), nullable=True),
            sa.Column("primary_email", sa.String(), nullable=True),
            sa.Column("primary_phone", sa.String(), nullable=True),
            sa.Column("lifecycle_stage", sa.String(), nullable=False,
                      server_default="new_lead"),
            sa.Column("source", sa.String(), nullable=True),
            sa.Column("preferred_channel", sa.String(), nullable=True),
            sa.Column("sticky_note", sa.Text(), nullable=True),
            sa.Column("assigned_loan_officer_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assigned_loan_assistant_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assigned_processor_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assigned_underwriter_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("property_address", postgresql.JSONB(), nullable=True),
            sa.Column("active_loan_program", sa.String(), nullable=True),
            sa.Column("active_loan_purpose", sa.String(), nullable=True),
            sa.Column("active_loan_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("active_loan_fico", sa.Integer(), nullable=True),
            sa.Column("active_loan_ltv", sa.Numeric(8, 4), nullable=True),
            sa.Column("active_loan_lock_expires_at",
                      sa.DateTime(timezone=True), nullable=True),
            sa.Column("active_loan_projected_close_date",
                      sa.DateTime(timezone=True), nullable=True),
            sa.Column("tags", postgresql.JSONB(), nullable=False,
                      server_default="[]"),
            sa.Column("last_contact_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
        )
        print("  Created table client_files")
    else:
        print("  Table client_files already exists — skipping")

    # ------------------------------------------------------------------
    # 3. client_file_collaborators  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "client_file_collaborators"):
        op.create_table(
            "client_file_collaborators",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(),
                      sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("client_file_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("client_files.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("role", sa.String(), nullable=False,
                      server_default="viewer"),
            sa.Column("notify_on_inbound", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.UniqueConstraint("client_file_id", "user_id",
                                name="uq_cf_collaborators_client_user"),
        )
        print("  Created table client_file_collaborators")
    else:
        print("  Table client_file_collaborators already exists — skipping")

    # ------------------------------------------------------------------
    # 4. team_chat_channels  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "team_chat_channels"):
        op.create_table(
            "team_chat_channels",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("client_file_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("client_files.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("pinned_message_id", postgresql.UUID(as_uuid=True),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.UniqueConstraint("client_file_id",
                                name="uq_team_chat_channels_client_file"),
        )
        print("  Created table team_chat_channels")
    else:
        print("  Table team_chat_channels already exists — skipping")

    # ------------------------------------------------------------------
    # 5. team_chat_messages  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "team_chat_messages"):
        op.create_table(
            "team_chat_messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("team_chat_channels.id",
                                    ondelete="CASCADE"),
                      nullable=False),
            sa.Column("client_file_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("client_files.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("author_kind",
                      postgresql.ENUM(name="team_chat_author_kind",
                                      create_type=False),
                      nullable=False),
            sa.Column("author_user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("system_agent_slug",
                      postgresql.ENUM(name="team_chat_agent_slug",
                                      create_type=False),
                      nullable=True),
            sa.Column("system_display_name", sa.String(80), nullable=True),
            sa.Column("system_source_event_kind", sa.String(80),
                      nullable=True),
            sa.Column("system_source_object_id",
                      postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("system_source_object_label", sa.String(200),
                      nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("mentioned_user_ids",
                      postgresql.ARRAY(sa.Integer()),
                      nullable=False, server_default="{}"),
            sa.Column("attachments", postgresql.JSONB(), nullable=False,
                      server_default="[]"),
            sa.Column("is_pinned", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        print("  Created table team_chat_messages")
    else:
        print("  Table team_chat_messages already exists — skipping")

    # Add pinned_message FK on channels (deferred due to circular ref)
    if _table_exists(conn, "team_chat_channels") and _table_exists(conn, "team_chat_messages"):
        op.execute("""
            DO $$ BEGIN
                ALTER TABLE team_chat_channels
                    ADD CONSTRAINT fk_tc_channels_pinned
                    FOREIGN KEY (pinned_message_id) REFERENCES team_chat_messages(id)
                    ON DELETE SET NULL;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)

    # ------------------------------------------------------------------
    # 6. team_chat_reactions  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "team_chat_reactions"):
        op.create_table(
            "team_chat_reactions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("message_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("team_chat_messages.id",
                                    ondelete="CASCADE"),
                      nullable=False),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("emoji",
                      postgresql.ENUM(name="team_chat_reaction_emoji",
                                      create_type=False),
                      nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.UniqueConstraint("message_id", "user_id", "emoji",
                                name="uq_team_chat_reactions_msg_user_emoji"),
        )
        print("  Created table team_chat_reactions")
    else:
        print("  Table team_chat_reactions already exists — skipping")

    # ------------------------------------------------------------------
    # 7. team_chat_reads  (migration 014 creates this)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "team_chat_reads"):
        op.create_table(
            "team_chat_reads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("team_chat_channels.id",
                                    ondelete="CASCADE"),
                      nullable=False),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("last_read_message_id", postgresql.UUID(as_uuid=True),
                      nullable=False),
            sa.Column("last_read_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("channel_id", "user_id",
                                name="uq_team_chat_reads_channel_user"),
        )
        print("  Created table team_chat_reads")
    else:
        print("  Table team_chat_reads already exists — skipping")

    # ------------------------------------------------------------------
    # 8. audit_events  (NEW — was only in start.py)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("outcome", sa.String(16), nullable=False,
                      server_default="success"),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("actor_email", sa.String(320), nullable=True),
            sa.Column("actor_role", sa.String(32), nullable=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("resource_type", sa.String(64), nullable=True),
            sa.Column("resource_id", sa.String(128), nullable=True),
            sa.Column("ip", postgresql.INET(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("metadata", postgresql.JSONB(), nullable=False,
                      server_default="{}"),
        )
        print("  Created table audit_events")
    else:
        print("  Table audit_events already exists — skipping")

    # ------------------------------------------------------------------
    # 9. ai_cost_records  (NEW — was only in start.py)
    # ------------------------------------------------------------------
    if not _table_exists(conn, "ai_cost_records"):
        op.create_table(
            "ai_cost_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Integer(),
                      sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("agent_type", sa.String(64), nullable=False),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )
        print("  Created table ai_cost_records")
    else:
        print("  Table ai_cost_records already exists — skipping")

    # ------------------------------------------------------------------
    # 10. Create indexes (all idempotent via IF NOT EXISTS check)
    # ------------------------------------------------------------------
    _indexes = [
        # team_chat indexes (migration 014 also creates these)
        ("ix_team_chat_channels_org", "team_chat_channels", ["organization_id"]),
        ("ix_tc_messages_channel_time", "team_chat_messages", ["channel_id", "created_at"]),
        ("ix_tc_messages_org", "team_chat_messages", ["organization_id"]),
        ("ix_tc_messages_client_file", "team_chat_messages", ["client_file_id"]),
        ("ix_tc_reactions_message", "team_chat_reactions", ["message_id"]),
        # audit_events indexes
        ("ix_audit_events_occurred", "audit_events", ["occurred_at"]),
        ("ix_audit_events_event_type", "audit_events", ["event_type"]),
        ("ix_audit_events_actor", "audit_events", ["actor_id"]),
        ("ix_audit_events_resource", "audit_events", ["resource_id"]),
        # ai_cost_records indexes
        ("ix_ai_cost_org_created", "ai_cost_records", ["organization_id", "created_at"]),
        ("ix_ai_cost_org_agent", "ai_cost_records", ["organization_id", "agent_type"]),
        ("ix_ai_cost_model", "ai_cost_records", ["model"]),
        ("ix_ai_cost_created", "ai_cost_records", ["created_at"]),
        ("ix_ai_cost_user", "ai_cost_records", ["user_id", "created_at"]),
    ]

    for idx_name, table, columns in _indexes:
        if _table_exists(conn, table) and not _index_exists(conn, idx_name):
            op.create_index(idx_name, table, columns)
            print(f"  Created index {idx_name}")
        else:
            print(f"  Index {idx_name} already exists or table missing — skipping")

    print("015: Inline DDL consolidation complete.")


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    """Drop tables added by this migration.

    Only drops audit_events and ai_cost_records (the tables that were
    NOT in migration 014). Tables from 014 are left for its own
    downgrade() to handle.
    """
    # Drop ai_cost_records indexes + table
    for idx in ("ix_ai_cost_user", "ix_ai_cost_created", "ix_ai_cost_model",
                "ix_ai_cost_org_agent", "ix_ai_cost_org_created"):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.execute("DROP TABLE IF EXISTS ai_cost_records")

    # Drop audit_events indexes + table
    for idx in ("ix_audit_events_resource", "ix_audit_events_actor",
                "ix_audit_events_event_type", "ix_audit_events_occurred"):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.execute("DROP TABLE IF EXISTS audit_events")
