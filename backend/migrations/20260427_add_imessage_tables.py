"""add imessage tables

Revision ID: 20260427_imessage
Revises: <PUT_YOUR_PREVIOUS_REVISION_HERE>
Create Date: 2026-04-27

This migration creates the five iMessage tables:
  - imessage_lines
  - imessage_threads
  - imessage_messages
  - imessage_lookup_cache
  - imessage_webhook_log
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_imessage"
down_revision = None  # set to your latest existing revision id
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- imessage_lines ----------------------------------------------------
    op.create_table(
        "imessage_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("handle", sa.String(120), nullable=False),
        sa.Column("bb_base_url", sa.Text, nullable=False),
        sa.Column("bb_password", sa.Text, nullable=True),
        sa.Column("cf_access_client_id", sa.Text, nullable=True),
        sa.Column("cf_access_client_secret", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ping_status", sa.String(16), nullable=True),
        sa.Column("daily_send_limit", sa.Integer, nullable=False, server_default="2500"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "handle", name="uq_imessage_line_tenant_handle"),
    )
    op.create_index("ix_imessage_line_tenant", "imessage_lines", ["tenant_id"])

    # ---- imessage_threads --------------------------------------------------
    op.create_table(
        "imessage_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("imessage_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("chat_guid", sa.String(120), nullable=True),
        sa.Column("last_known_service", sa.String(16), nullable=True),
        sa.Column("is_group", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("participants", postgresql.JSONB, nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "contact_id", "line_id", name="uq_imessage_thread"),
    )
    op.create_index("ix_imessage_thread_chat_guid", "imessage_threads", ["chat_guid"])

    # ---- imessage_messages -------------------------------------------------
    op.create_table(
        "imessage_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("imessage_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_seat_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("body", sa.Text, nullable=True),  # actual type is EncryptedText
        sa.Column("media_urls", postgresql.JSONB, nullable=True),
        sa.Column("send_style", sa.String(32), nullable=True),
        sa.Column("bb_message_guid", sa.String(64), nullable=True),
        sa.Column("bb_temp_guid", sa.String(64), nullable=True),
        sa.Column("bb_chat_guid", sa.String(120), nullable=True),
        sa.Column("associated_message_guid", sa.String(64), nullable=True),
        sa.Column("tapback", sa.String(16), nullable=True),
        sa.Column("reply_to_message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("imessage_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("bb_message_guid", name="uq_imessage_messages_bb_guid"),
    )
    op.create_index(
        "ix_imessage_thread_created", "imessage_messages",
        ["thread_id", "created_at"],
    )
    op.create_index("ix_imessage_temp_guid", "imessage_messages", ["bb_temp_guid"])
    op.create_index("ix_imessage_status", "imessage_messages", ["status"])

    # ---- imessage_lookup_cache --------------------------------------------
    op.create_table(
        "imessage_lookup_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("line_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("imessage_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handle", sa.String(120), nullable=False),
        sa.Column("service", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("line_id", "handle", name="uq_imessage_lookup"),
    )
    op.create_index(
        "ix_imessage_lookup_checked_at", "imessage_lookup_cache", ["checked_at"]
    )

    # ---- imessage_webhook_log ---------------------------------------------
    op.create_table(
        "imessage_webhook_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("line_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("imessage_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("bb_guid", sa.String(64), nullable=True),
        sa.Column("event_signature", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("processed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("processing_error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_imessage_webhook_dedupe",
        "imessage_webhook_log",
        ["event_type", "bb_guid", "event_signature"],
        unique=True,
    )
    op.create_index(
        "ix_imessage_webhook_received_at", "imessage_webhook_log", ["received_at"]
    )


def downgrade() -> None:
    op.drop_table("imessage_webhook_log")
    op.drop_table("imessage_lookup_cache")
    op.drop_table("imessage_messages")
    op.drop_table("imessage_threads")
    op.drop_table("imessage_lines")
