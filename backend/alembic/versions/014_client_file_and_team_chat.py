"""client_file aggregate root + team chat tables

Revision ID: 014_client_file_and_team_chat
Revises: 013_rls_remaining_tables
Create Date: 2026-05-02

Creates 6 tables:
  client_files             — UUID aggregate root, one per lead
  client_file_collaborators — per-file user assignments
  team_chat_channels       — one per client file (UNIQUE)
  team_chat_messages       — human + system bot messages
  team_chat_reactions      — 4-emoji reaction set
  team_chat_reads          — per-user read cursor

Plus 3 enum types, indexes (GIN on mentioned_user_ids), RLS on all tables,
and an updated_at trigger on client_files.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014_client_file_and_team_chat"
down_revision = "013_rls_remaining_tables"
branch_labels = None
depends_on = None

AUTHOR_KIND_ENUM = "team_chat_author_kind"
AGENT_SLUG_ENUM = "team_chat_agent_slug"
REACTION_EMOJI_ENUM = "team_chat_reaction_emoji"

RLS_EXPR = "organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_org_isolation ON {table} "
        f"USING ({RLS_EXPR}) WITH CHECK ({RLS_EXPR})"
    )


def upgrade() -> None:
    # ── client_files ─────────────────────────────────────────────────
    op.create_table(
        "client_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Integer(),
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lead_id", sa.Integer(),
                  sa.ForeignKey("leads.id"), nullable=True, unique=True),
        # Identity
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("primary_email", sa.String(), nullable=True),
        sa.Column("primary_phone", sa.String(), nullable=True),
        sa.Column("lifecycle_stage", sa.String(), nullable=False,
                  server_default="new_lead"),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("preferred_channel", sa.String(), nullable=True),
        sa.Column("sticky_note", sa.Text(), nullable=True),
        # Assignment
        sa.Column("assigned_loan_officer_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_loan_assistant_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_processor_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_underwriter_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        # Loan rollups
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
        # Metadata
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
    op.create_index("ix_client_files_org", "client_files",
                    ["organization_id"])
    op.create_index("ix_client_files_lead", "client_files", ["lead_id"])
    op.create_index("ix_client_files_assigned_lo", "client_files",
                    ["assigned_loan_officer_id"])
    op.create_index("ix_client_files_assigned_uw", "client_files",
                    ["assigned_underwriter_id"])
    op.create_index("ix_client_files_lifecycle", "client_files",
                    ["organization_id", "lifecycle_stage"])
    op.create_index("ix_client_files_tags", "client_files", ["tags"],
                    postgresql_using="gin")

    # updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_client_files_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_client_files_updated_at
            BEFORE UPDATE ON client_files
            FOR EACH ROW EXECUTE FUNCTION update_client_files_updated_at()
    """)

    # ── client_file_collaborators ────────────────────────────────────
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
    op.create_index("ix_cf_collaborators_client",
                    "client_file_collaborators", ["client_file_id"])
    op.create_index("ix_cf_collaborators_user",
                    "client_file_collaborators", ["user_id"])

    # ── Team chat enum types ─────────────────────────────────────────
    op.execute(
        f"CREATE TYPE {AUTHOR_KIND_ENUM} AS ENUM ('human', 'system')"
    )
    op.execute(
        f"CREATE TYPE {AGENT_SLUG_ENUM} AS ENUM ("
        f"'cadence', 'aria', 'avery', 'insight', 'ops_manager', "
        f"'document', 'milestone', 'lifecycle')"
    )
    op.execute(
        f"CREATE TYPE {REACTION_EMOJI_ENUM} AS ENUM ("
        f"'thumbs_up', 'check', 'fire', 'question')"
    )

    # ── team_chat_channels (without pinned_message FK) ───────────────
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
    op.create_index("ix_team_chat_channels_org", "team_chat_channels",
                    ["organization_id"])

    # ── team_chat_messages ───────────────────────────────────────────
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
                  postgresql.ENUM(name=AUTHOR_KIND_ENUM,
                                  create_type=False),
                  nullable=False),
        sa.Column("author_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("system_agent_slug",
                  postgresql.ENUM(name=AGENT_SLUG_ENUM,
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
    op.create_index("ix_team_chat_messages_channel_time",
                    "team_chat_messages", ["channel_id", "created_at"])
    op.create_index("ix_team_chat_messages_org",
                    "team_chat_messages", ["organization_id"])
    op.create_index("ix_team_chat_messages_client_file",
                    "team_chat_messages", ["client_file_id"])
    op.create_index("ix_team_chat_messages_mentions",
                    "team_chat_messages", ["mentioned_user_ids"],
                    postgresql_using="gin")

    # Now add the channel→message FK for pinned_message_id
    op.create_foreign_key(
        "fk_team_chat_channels_pinned_message",
        source_table="team_chat_channels",
        referent_table="team_chat_messages",
        local_cols=["pinned_message_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ── team_chat_reactions ──────────────────────────────────────────
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
                  postgresql.ENUM(name=REACTION_EMOJI_ENUM,
                                  create_type=False),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("message_id", "user_id", "emoji",
                            name="uq_team_chat_reactions_msg_user_emoji"),
    )
    op.create_index("ix_team_chat_reactions_message",
                    "team_chat_reactions", ["message_id"])

    # ── team_chat_reads ──────────────────────────────────────────────
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

    # ── Enable RLS on all 6 tables ───────────────────────────────────
    for tbl in (
        "client_files",
        "client_file_collaborators",
        "team_chat_channels",
        "team_chat_messages",
        "team_chat_reactions",
        "team_chat_reads",
    ):
        _enable_rls(tbl)


def downgrade() -> None:
    op.drop_constraint("fk_team_chat_channels_pinned_message",
                       "team_chat_channels", type_="foreignkey")
    op.drop_table("team_chat_reads")
    op.drop_index("ix_team_chat_reactions_message",
                  table_name="team_chat_reactions")
    op.drop_table("team_chat_reactions")
    op.drop_index("ix_team_chat_messages_mentions",
                  table_name="team_chat_messages")
    op.drop_index("ix_team_chat_messages_client_file",
                  table_name="team_chat_messages")
    op.drop_index("ix_team_chat_messages_org",
                  table_name="team_chat_messages")
    op.drop_index("ix_team_chat_messages_channel_time",
                  table_name="team_chat_messages")
    op.drop_table("team_chat_messages")
    op.drop_index("ix_team_chat_channels_org",
                  table_name="team_chat_channels")
    op.drop_table("team_chat_channels")
    op.execute(f"DROP TYPE IF EXISTS {REACTION_EMOJI_ENUM}")
    op.execute(f"DROP TYPE IF EXISTS {AGENT_SLUG_ENUM}")
    op.execute(f"DROP TYPE IF EXISTS {AUTHOR_KIND_ENUM}")
    op.drop_index("ix_cf_collaborators_user",
                  table_name="client_file_collaborators")
    op.drop_index("ix_cf_collaborators_client",
                  table_name="client_file_collaborators")
    op.drop_table("client_file_collaborators")
    op.execute("DROP TRIGGER IF EXISTS trg_client_files_updated_at ON client_files")
    op.execute("DROP FUNCTION IF EXISTS update_client_files_updated_at()")
    op.drop_index("ix_client_files_tags", table_name="client_files")
    op.drop_index("ix_client_files_lifecycle", table_name="client_files")
    op.drop_index("ix_client_files_assigned_uw", table_name="client_files")
    op.drop_index("ix_client_files_assigned_lo", table_name="client_files")
    op.drop_index("ix_client_files_lead", table_name="client_files")
    op.drop_index("ix_client_files_org", table_name="client_files")
    op.drop_table("client_files")
