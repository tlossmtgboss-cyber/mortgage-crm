# Client File Aggregate Root + Team Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `client_files` aggregate root table, backfill from leads, adapt and install the LO Surface team chat package, and wire up the frontend 3-pane client file view.

**Architecture:** `client_files` (UUID PK) is the first UUID-PK table — the aggregate root that leads, loans, threads, and documents hang off. Integer FKs link to existing `users`/`organizations` tables. A bridge column (`lead_id`) enables old-to-new schema transition. Team chat uses 4 adapted tables (channels, messages, reactions, reads) with RLS via `app.current_tenant` (Integer cast). A Redis Stream consumer worker posts system messages. All service methods are sync (plain `def`).

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL (Railway 14+), Redis Streams, React 18 + @tanstack/react-query, Alembic migrations.

---

## File Map

### New files (create)

| File | Responsibility |
|---|---|
| `backend/database/models/client_file.py` | `ClientFile` + `ClientFileCollaborator` SQLAlchemy models |
| `backend/database/models/team_chat.py` | 4 team chat models + 3 enum classes (adapted from package) |
| `backend/services/client_file_service.py` | `ensure_client_file(db, lead)` hook |
| `backend/services/team_chat.py` | `TeamChatService` (adapted from package) |
| `backend/routes/team_chat_routes.py` | 14 FastAPI endpoints (adapted from package) |
| `backend/workers/team_chat_bot.py` | Redis Stream consumer (adapted from package) |
| `backend/alembic/versions/014_client_file_and_team_chat.py` | Single Alembic migration for all 6 new tables |
| `backend/migrations/backfill_client_files.py` | ORM-based backfill script |
| `backend/tests/test_client_file_service.py` | Tests for `ensure_client_file` |
| `backend/tests/test_team_chat_service.py` | Tests for `TeamChatService` |
| `backend/tests/test_team_chat_routes.py` | Tests for team chat API endpoints |
| `frontend/src/client-file/` (16 files) | 3-pane view + team chat (copied from package) |
| `frontend/src/pages/ClientFilePage.jsx` | Route wrapper for `ClientFileView` |

### Modified files

| File | Change |
|---|---|
| `backend/database/models/__init__.py` | Add imports for `ClientFile`, `ClientFileCollaborator`, team chat models |
| `backend/routes/inline_legacy_routes.py:1060-1066` | Add team chat router registration after leads_crud |
| `backend/routes/leads_crud_routes.py` | Add bridge endpoint `GET /leads/{lead_id}/client-file-id` + hook `ensure_client_file` into `POST /leads/` |
| `backend/tests/conftest.py` | Add `sample_client_file` fixture |
| `frontend/src/routes/index.jsx` | Add `/clients/:uuid` route + lazy import |
| `frontend/src/pages/LeadDetail.js` | Add "Open in Client File" link |
| 27 other backend files | Add `ensure_client_file(db, lead)` call after `db.flush()` in each lead creation path |

---

## Task 1: Alembic Migration — 6 New Tables

**Files:**
- Create: `backend/alembic/versions/014_client_file_and_team_chat.py`

- [ ] **Step 1: Write the migration file**

```python
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
```

- [ ] **Step 2: Dry-run the migration to verify SQL**

Run: `cd backend && alembic upgrade --sql 014_client_file_and_team_chat > /tmp/014_migration.sql && head -100 /tmp/014_migration.sql`

Expected: Valid SQL with CREATE TABLE, CREATE INDEX, CREATE POLICY statements. No errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/014_client_file_and_team_chat.py
git commit -m "feat: migration — client_files aggregate root + team chat tables (6 tables, RLS)"
```

---

## Task 2: ClientFile + ClientFileCollaborator Models

**Files:**
- Create: `backend/database/models/client_file.py`
- Modify: `backend/database/models/__init__.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_client_file_model.py`:

```python
"""Test ClientFile and ClientFileCollaborator model definitions."""
import uuid
from database.models.client_file import ClientFile, ClientFileCollaborator


def test_client_file_has_uuid_pk():
    cf = ClientFile(
        organization_id=1,
        first_name="John",
        last_name="Doe",
        lifecycle_stage="new_lead",
    )
    assert cf.organization_id == 1
    assert cf.lifecycle_stage == "new_lead"


def test_client_file_collaborator_has_uuid_pk():
    collab = ClientFileCollaborator(
        organization_id=1,
        client_file_id=uuid.uuid4(),
        user_id=1,
        role="viewer",
    )
    assert collab.role == "viewer"
    assert collab.user_id == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_client_file_model.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'database.models.client_file'`

- [ ] **Step 3: Write the ClientFile model**

Create `backend/database/models/client_file.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ClientFile(Base):
    __tablename__ = "client_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False
    )
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leads.id"), nullable=True, unique=True
    )

    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    primary_email: Mapped[Optional[str]] = mapped_column(String)
    primary_phone: Mapped[Optional[str]] = mapped_column(String)
    lifecycle_stage: Mapped[str] = mapped_column(
        String, nullable=False, server_default="new_lead"
    )
    source: Mapped[Optional[str]] = mapped_column(String)
    preferred_channel: Mapped[Optional[str]] = mapped_column(String)
    sticky_note: Mapped[Optional[str]] = mapped_column(Text)

    assigned_loan_officer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_loan_assistant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_processor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_underwriter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )

    property_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    active_loan_program: Mapped[Optional[str]] = mapped_column(String)
    active_loan_purpose: Mapped[Optional[str]] = mapped_column(String)
    active_loan_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    active_loan_fico: Mapped[Optional[int]] = mapped_column(Integer)
    active_loan_ltv: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    active_loan_lock_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    active_loan_projected_close_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now()
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )


class ClientFileCollaborator(Base):
    __tablename__ = "client_file_collaborators"
    __table_args__ = (
        UniqueConstraint("client_file_id", "user_id",
                         name="uq_cf_collaborators_client_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False
    )
    client_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_files.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="viewer")
    notify_on_inbound: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Register models in `__init__.py`**

Add to `backend/database/models/__init__.py` after the iMessage import block (line 656) and before `__all__`:

```python
# Client File aggregate root + collaborators
from .client_file import ClientFile, ClientFileCollaborator
```

Add to `__all__` before the closing bracket:

```python
    # =====================
    # Client File Aggregate
    # =====================
    "ClientFile",
    "ClientFileCollaborator",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_client_file_model.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/database/models/client_file.py backend/database/models/__init__.py backend/tests/test_client_file_model.py
git commit -m "feat: ClientFile + ClientFileCollaborator models (UUID PK, Integer FKs)"
```

---

## Task 3: Team Chat Models (Adapted from Package)

**Files:**
- Create: `backend/database/models/team_chat.py`
- Modify: `backend/database/models/__init__.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_team_chat_model.py`:

```python
"""Test team chat model definitions — verify Integer user FKs and UUID PKs."""
import uuid
from database.models.team_chat import (
    TeamChatAuthorKind,
    TeamChatAgentSlug,
    TeamChatReactionEmoji,
    TeamChatChannel,
    TeamChatMessage,
    TeamChatReaction,
    TeamChatRead,
)


def test_author_kind_enum():
    assert TeamChatAuthorKind.HUMAN.value == "human"
    assert TeamChatAuthorKind.SYSTEM.value == "system"


def test_channel_uses_integer_org_id():
    ch = TeamChatChannel(organization_id=1, client_file_id=uuid.uuid4())
    assert ch.organization_id == 1


def test_message_uses_integer_author():
    msg = TeamChatMessage(
        organization_id=1,
        channel_id=uuid.uuid4(),
        client_file_id=uuid.uuid4(),
        author_kind=TeamChatAuthorKind.HUMAN,
        author_user_id=42,
        body="hello",
    )
    assert msg.author_user_id == 42


def test_reaction_uses_integer_user():
    r = TeamChatReaction(
        organization_id=1,
        message_id=uuid.uuid4(),
        user_id=7,
        emoji=TeamChatReactionEmoji.THUMBS_UP,
    )
    assert r.user_id == 7


def test_read_uses_integer_user():
    rd = TeamChatRead(
        organization_id=1,
        channel_id=uuid.uuid4(),
        user_id=3,
        last_read_message_id=uuid.uuid4(),
    )
    assert rd.user_id == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_team_chat_model.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'database.models.team_chat'`

- [ ] **Step 3: Create the adapted team chat models**

Copy `/tmp/lo_surface/extracted/perennia_lo_surface/backend/app/models/team_chat.py` to `backend/database/models/team_chat.py` and apply these changes:

1. Replace `from app.db.base import Base` with `from db import Base`
2. Rename all `org_id` columns to `organization_id`
3. Change `organization_id` type from `UUID(as_uuid=True)` to `Integer`
4. Change `author_user_id` type from `UUID(as_uuid=True), ForeignKey("users.id", ...)` to `Integer, ForeignKey("users.id", ...)`
5. Change `user_id` in reactions and reads from `UUID(as_uuid=True)` to `Integer`
6. Change `mentioned_user_ids` from `ARRAY(UUID(as_uuid=True))` to `ARRAY(Integer)`
7. Update index names from `"org_id"` to `"organization_id"` in `__table_args__`

Key columns that stay UUID: `id`, `channel_id`, `client_file_id`, `message_id`, `pinned_message_id`, `last_read_message_id`, `system_source_object_id`.

- [ ] **Step 4: Register in `__init__.py`**

Add to `backend/database/models/__init__.py` after the ClientFile import:

```python
# Team Chat models
from .team_chat import (
    TeamChatChannel,
    TeamChatMessage,
    TeamChatReaction,
    TeamChatRead,
    TeamChatAuthorKind,
    TeamChatAgentSlug,
    TeamChatReactionEmoji,
)
```

Add to `__all__`:

```python
    # =====================
    # Team Chat
    # =====================
    "TeamChatChannel",
    "TeamChatMessage",
    "TeamChatReaction",
    "TeamChatRead",
    "TeamChatAuthorKind",
    "TeamChatAgentSlug",
    "TeamChatReactionEmoji",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_team_chat_model.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/database/models/team_chat.py backend/database/models/__init__.py backend/tests/test_team_chat_model.py
git commit -m "feat: team chat models — Integer user FKs, UUID channel/message PKs"
```

---

## Task 4: `ensure_client_file` Service + Tests

**Files:**
- Create: `backend/services/client_file_service.py`
- Create: `backend/tests/test_client_file_service.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_client_file_service.py`:

```python
"""Test ensure_client_file — the hook called on every lead creation path."""
import pytest
from unittest.mock import MagicMock
from services.client_file_service import ensure_client_file


def test_ensure_client_file_creates_new(db_session):
    from database.models import Lead
    lead = Lead(
        organization_id=1,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="+15551234567",
        source="website",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()

    cf = ensure_client_file(db_session, lead)

    assert cf is not None
    assert cf.lead_id == lead.id
    assert cf.first_name == "Jane"
    assert cf.last_name == "Doe"
    assert cf.primary_email == "jane@example.com"
    assert cf.organization_id == 1
    assert cf.lifecycle_stage == "new_lead"
    assert cf.assigned_loan_officer_id == 1


def test_ensure_client_file_is_idempotent(db_session):
    from database.models import Lead
    lead = Lead(
        organization_id=1,
        first_name="Bob",
        last_name="Smith",
        email="bob@example.com",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()

    cf1 = ensure_client_file(db_session, lead)
    cf2 = ensure_client_file(db_session, lead)

    assert cf1.id == cf2.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_client_file_service.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'services.client_file_service'`

- [ ] **Step 3: Write the service**

Create `backend/services/client_file_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.client_file import ClientFile


def ensure_client_file(db: Session, lead) -> ClientFile:
    existing = db.execute(
        select(ClientFile).where(ClientFile.lead_id == lead.id)
    ).scalar_one_or_none()
    if existing:
        return existing
    cf = ClientFile(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        primary_email=lead.email,
        primary_phone=lead.phone,
        lifecycle_stage="new_lead",
        source=lead.source,
        assigned_loan_officer_id=lead.owner_id,
    )
    db.add(cf)
    db.flush()
    return cf
```

- [ ] **Step 4: Add `sample_client_file` fixture to conftest.py**

Add to `backend/tests/conftest.py` after the `sample_loan` fixture (around line 414):

```python
@pytest.fixture
def sample_client_file(db_session):
    """Create a real ClientFile linked to a real Lead in the test DB."""
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(
        organization_id=1,
        first_name="Test",
        last_name="Client",
        email="test.client@example.com",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()
    return cf
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_client_file_service.py -v`

Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add backend/services/client_file_service.py backend/tests/test_client_file_service.py backend/tests/conftest.py
git commit -m "feat: ensure_client_file service + test fixture"
```

---

## Task 5: TeamChatService (Adapted from Package)

**Files:**
- Create: `backend/services/team_chat.py`
- Create: `backend/tests/test_team_chat_service.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_team_chat_service.py`:

```python
"""Test TeamChatService — channel creation, messages, reactions, read cursors."""
import uuid
import pytest
from services.team_chat import TeamChatService
from database.models.team_chat import TeamChatAuthorKind, TeamChatReactionEmoji


def test_get_or_create_channel(db_session, sample_client_file):
    svc = TeamChatService(db_session, redis=None)
    ch = svc.get_or_create_channel(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
    )
    assert ch is not None
    assert ch.client_file_id == sample_client_file.id

    ch2 = svc.get_or_create_channel(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
    )
    assert ch.id == ch2.id


def test_post_human_message(db_session, sample_client_file):
    svc = TeamChatService(db_session, redis=None)
    msg = svc.post_human_message(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
        author_user_id=1,
        body="Hello team!",
    )
    assert msg.body == "Hello team!"
    assert msg.author_kind == TeamChatAuthorKind.HUMAN
    assert msg.author_user_id == 1


def test_post_system_message(db_session, sample_client_file):
    from database.models.team_chat import TeamChatAgentSlug
    svc = TeamChatService(db_session, redis=None)
    msg = svc.post_system_message(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
        agent_slug=TeamChatAgentSlug.CADENCE,
        display_name="Cadence Agent",
        body="sent SMS",
    )
    assert msg.author_kind == TeamChatAuthorKind.SYSTEM
    assert msg.system_agent_slug == TeamChatAgentSlug.CADENCE


def test_react_and_unreact(db_session, sample_client_file):
    svc = TeamChatService(db_session, redis=None)
    msg = svc.post_human_message(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
        author_user_id=1,
        body="react to this",
    )
    r = svc.react(
        message_id=msg.id,
        user_id=1,
        emoji=TeamChatReactionEmoji.THUMBS_UP,
        organization_id=sample_client_file.organization_id,
    )
    assert r.emoji == TeamChatReactionEmoji.THUMBS_UP

    svc.unreact(message_id=msg.id, user_id=1, emoji=TeamChatReactionEmoji.THUMBS_UP)


def test_unread_count(db_session, sample_client_file):
    svc = TeamChatService(db_session, redis=None)
    svc.post_human_message(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
        author_user_id=2,
        body="message from user 2",
    )
    counts = svc.unread_count(
        organization_id=sample_client_file.organization_id,
        client_file_id=sample_client_file.id,
        user_id=99,
    )
    assert counts["unread"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_team_chat_service.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'services.team_chat'`

- [ ] **Step 3: Copy and adapt the service**

Copy `/tmp/lo_surface/extracted/perennia_lo_surface/backend/app/services/team_chat.py` to `backend/services/team_chat.py` and apply these changes:

1. `from app.models import ClientFile, User` → `from database.models import ClientFile, User`
2. `from app.models.team_chat import ...` → `from database.models.team_chat import ...`
3. All `org_id` parameter names → `organization_id` (in method signatures, kwargs, and comparisons)
4. `TeamChatChannel.org_id` → `TeamChatChannel.organization_id` (and same for Message, etc.)
5. `client.org_id` → `client.organization_id`
6. In `_user_display_name()`: remove `getattr(u, "display_name", None)` fallback — User has no `display_name`. Keep only `first_name + " " + last_name` pattern.
7. In `list_members()`: `u.last_active_at` → `u.last_activity_at`
8. In `list_members()`: Replace the `from app.models import Collaborator` try-block with:
   ```python
   from database.models.client_file import ClientFileCollaborator
   collabs = list(
       self.session.execute(
           select(ClientFileCollaborator).where(
               and_(
                   ClientFileCollaborator.organization_id == organization_id,
                   ClientFileCollaborator.client_file_id == client_file_id,
               )
           )
       ).scalars().all()
   )
   for c in collabs:
       if c.user_id:
           member_user_ids.add(c.user_id)
   ```
9. All `uuid.UUID` type hints for user IDs → `int` (in method signatures and dataclass fields)
10. In `ReactionSummary`: `user_ids: list[int]`, and `"user_ids": [str(u) for u in self.user_ids]` stays as-is (frontend expects strings)
11. In `_typing_key` and `_online_key`: parameter types stay as they are (channel_id is UUID, organization_id is int)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_team_chat_service.py -v`

Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/team_chat.py backend/tests/test_team_chat_service.py
git commit -m "feat: TeamChatService — adapted from package (Integer user IDs, org_id→organization_id)"
```

---

## Task 6: Team Chat Routes (Adapted from Package)

**Files:**
- Create: `backend/routes/team_chat_routes.py`
- Create: `backend/tests/test_team_chat_routes.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_team_chat_routes.py`:

```python
"""Test team chat API endpoints."""
import uuid
import pytest


def test_send_message_returns_201(authenticated_client, db_session):
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(organization_id=1, first_name="Route", last_name="Test",
                email="rt@test.com", owner_id=1)
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()

    resp = authenticated_client.post(
        f"/api/v1/clients/{cf.id}/team-chat/messages",
        json={"body": "Hello from test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "Hello from test"
    assert data["author"]["kind"] == "human"


def test_list_messages_returns_200(authenticated_client, db_session):
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(organization_id=1, first_name="List", last_name="Test",
                email="lt@test.com", owner_id=1)
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()

    resp = authenticated_client.get(
        f"/api/v1/clients/{cf.id}/team-chat/messages"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_team_chat_routes.py -v`

Expected: FAIL — 404 (route not registered yet)

- [ ] **Step 3: Copy and adapt the routes**

Copy `/tmp/lo_surface/extracted/perennia_lo_surface/backend/app/api/routes/team_chat.py` to `backend/routes/team_chat_routes.py` and apply:

1. Replace the import block at top:
   ```python
   from app.api.deps import get_current_user, get_db, get_redis
   from app.models.team_chat import TeamChatReactionEmoji
   from app.services.team_chat import TeamChatService
   ```
   With:
   ```python
   from db import get_db

   def get_current_user_dep():
       from auth.dependencies import get_current_user
       return get_current_user

   def get_redis():
       from services.redis_service import get_redis_client
       return get_redis_client()

   def _get_models():
       from database.models.team_chat import TeamChatReactionEmoji
       return TeamChatReactionEmoji

   def _get_service():
       from services.team_chat import TeamChatService
       return TeamChatService
   ```
2. Every `Depends(get_current_user)` → `Depends(get_current_user_dep())`
3. Every `Depends(get_redis)` → keep as-is (local `get_redis` function)
4. Every `user.org_id` → `user.organization_id`
5. In `_svc()` helper: lazy import `TeamChatService`
6. In `_own_message_or_403`: `from app.models.team_chat import TeamChatMessage` → `from database.models.team_chat import TeamChatMessage`
7. `SendMessageBody.mentioned_user_ids` type: `list[uuid.UUID]` → `list[int]` (user IDs are Integer)

- [ ] **Step 4: Register the router in `inline_legacy_routes.py`**

Add after line 1066 in `backend/routes/inline_legacy_routes.py` (after the Leads CRUD block):

```python
    # Include Team Chat routes
    try:
        from routes.team_chat_routes import router as team_chat_router
        app.include_router(team_chat_router, prefix="/api/v1", tags=["Team Chat"])
        logger.info("✅ Team Chat routes loaded")
    except Exception as e:
        logger.warning(f"⚠️ Could not load Team Chat routes: {e}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_team_chat_routes.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/team_chat_routes.py backend/routes/inline_legacy_routes.py backend/tests/test_team_chat_routes.py
git commit -m "feat: team chat routes — 14 endpoints, adapted imports, router registered"
```

---

## Task 7: Team Chat Bot Worker (Adapted from Package)

**Files:**
- Create: `backend/workers/team_chat_bot.py`

- [ ] **Step 1: Create the workers directory if needed**

Run: `mkdir -p backend/workers && touch backend/workers/__init__.py`

- [ ] **Step 2: Copy and adapt the worker**

Copy `/tmp/lo_surface/extracted/perennia_lo_surface/backend/app/workers/team_chat_bot.py` to `backend/workers/team_chat_bot.py` and apply:

1. `from app.db.base import session_factory` → `from db import SessionLocal`
2. `from app.models.team_chat import TeamChatAgentSlug` → `from database.models.team_chat import TeamChatAgentSlug`
3. `from app.services.team_chat import TeamChatService` → `from services.team_chat import TeamChatService`
4. In `_scoped_session()`: `session = session_factory()` → `session = SessionLocal()`
5. In all event mappers: `uuid.UUID(event["org_id"])` → `int(event["org_id"])` (organization_id is Integer)
6. In `_process_event`, after `event = json.loads(payload_raw)` and before the handler call, add bridge resolution:
   ```python
   if "client_file_id" not in event and "lead_id" in event:
       with _scoped_session() as session:
           from database.models.client_file import ClientFile
           row = session.execute(
               select(ClientFile.id).where(
                   ClientFile.lead_id == int(event["lead_id"])
               )
           ).scalar_one_or_none()
           if row is None:
               logger.warning(
                   "team_chat_bot.no_client_file_for_lead",
                   extra={"lead_id": event["lead_id"]},
               )
               return
           event["client_file_id"] = str(row)
   ```
7. In the system message posting block: pass `organization_id=org_id` instead of `org_id=org_id`
8. In `main()`: replace `redis.from_url(redis_url)` with:
   ```python
   from services.redis_service import get_redis_client
   redis_client = get_redis_client()
   if redis_client is None:
       import redis as redis_lib
       redis_client = redis_lib.from_url(redis_url)
   ```

- [ ] **Step 3: Verify the worker imports cleanly**

Run: `cd backend && python -c "from workers.team_chat_bot import EVENT_HANDLERS, STREAMS; print(f'{len(EVENT_HANDLERS)} handlers, {len(STREAMS)} streams')"`

Expected: `9 handlers, 5 streams`

- [ ] **Step 4: Commit**

```bash
git add backend/workers/team_chat_bot.py backend/workers/__init__.py
git commit -m "feat: team chat bot worker — Redis Stream consumer with bridge resolution"
```

---

## Task 8: Backfill Script

**Files:**
- Create: `backend/migrations/backfill_client_files.py`

- [ ] **Step 1: Write the backfill script**

The script is defined in the spec (section 3.4). Create `backend/migrations/backfill_client_files.py` with the exact code from the spec:

```python
import logging
from db import SessionLocal
from database.models import Lead
from database.models.client_file import ClientFile

logger = logging.getLogger(__name__)

STAGE_MAP = {
    'FUNDED': 'closed_active',
    'CANCELLED': 'dead', 'DENIED': 'dead', 'DEAD': 'dead',
    'WITHDRAWN': 'dead', 'DOES_NOT_QUALIFY': 'dead',
    'NURTURE': 'nurture',
    'APPLICATION': 'pre_app', 'DISCLOSED': 'pre_app',
    'PROCESSING': 'in_processing', 'SUBMITTED': 'in_processing',
    'UNDERWRITING': 'in_underwriting', 'UW_RECEIVED': 'in_underwriting',
    'CONDITIONAL_APPROVAL': 'in_underwriting', 'APPROVED': 'in_underwriting',
    'SUSPENDED': 'in_underwriting',
    'CTC': 'clear_to_close', 'CLEAR_TO_CLOSE': 'clear_to_close',
    'CLOSING': 'clear_to_close', 'DOCS': 'clear_to_close',
    'DOCS_OUT': 'clear_to_close',
}

BATCH_SIZE = 500

def backfill():
    db = SessionLocal()
    try:
        total = db.query(Lead).count()
        logger.info(f"Backfilling client_files from {total} leads")
        created = 0
        skipped = 0
        for lead in db.query(Lead).yield_per(BATCH_SIZE):
            existing = db.query(ClientFile).filter(
                ClientFile.lead_id == lead.id
            ).first()
            if existing:
                skipped += 1
                continue
            prop_addr = None
            if lead.city:
                prop_addr = {
                    'city': lead.city, 'state': lead.state,
                    'zip': lead.zip_code, 'street': lead.address,
                }
            cf = ClientFile(
                organization_id=lead.organization_id,
                lead_id=lead.id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                primary_email=lead.email,
                primary_phone=lead.phone,
                lifecycle_stage=STAGE_MAP.get(
                    (lead.stage or '').upper(), 'new_lead'
                ),
                source=lead.source,
                preferred_channel=lead.preferred_communication,
                assigned_loan_officer_id=lead.owner_id,
                property_address=prop_addr,
                active_loan_program=lead.program,
                active_loan_purpose=lead.loan_purpose,
                active_loan_amount=lead.loan_amount,
                active_loan_fico=lead.credit_score,
                active_loan_ltv=lead.ltv,
                active_loan_lock_expires_at=lead.lock_expiration,
                active_loan_projected_close_date=lead.closing_date,
                last_contact_at=lead.last_contact,
            )
            db.add(cf)
            created += 1
            if created % BATCH_SIZE == 0:
                db.commit()
                logger.info(f"  committed batch: {created} created, {skipped} skipped")
        db.commit()
        logger.info(f"Backfill complete: {created} created, {skipped} skipped (of {total} leads)")
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill()
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd backend && python -c "from migrations.backfill_client_files import STAGE_MAP; print(f'{len(STAGE_MAP)} stage mappings')"`

Expected: `18 stage mappings`

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/backfill_client_files.py
git commit -m "feat: backfill script — ORM-based lead→client_file with batch commits"
```

---

## Task 9: Hook `ensure_client_file` into All 28 Lead Creation Paths

**Files:**
- Modify: 28 files listed in spec section 4.7

- [ ] **Step 1: Hook the primary path — `leads_crud_routes.py`**

In `backend/routes/leads_crud_routes.py`, after line 127 (`db.add(db_lead)`) and `db.commit()` / `db.refresh(db_lead)`:

The current flow is:
```python
db.add(db_lead)
db.commit()
db.refresh(db_lead)
```

Change `db.commit()` to `db.flush()`, add the hook, then commit:
```python
db.add(db_lead)
db.flush()

from services.client_file_service import ensure_client_file
ensure_client_file(db, db_lead)

db.commit()
db.refresh(db_lead)
```

- [ ] **Step 2: Also add the bridge endpoint to `leads_crud_routes.py`**

Add at the bottom of `backend/routes/leads_crud_routes.py`:

```python
@router.get("/{lead_id}/client-file-id")
def get_client_file_id_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    from database.models.client_file import ClientFile
    cf = db.execute(
        select(ClientFile.id).where(ClientFile.lead_id == lead_id)
    ).scalar_one_or_none()
    if cf is None:
        raise HTTPException(404, "no client file for this lead")
    return {"client_file_id": str(cf)}
```

Add `select` to the sqlalchemy imports at the top if not already there.

- [ ] **Step 3: Hook the remaining 27 paths**

For each file in the table below, find the `db.add(lead); db.flush()` (or `db.commit()`) pattern and add the hook call immediately after `flush()`. Use the lazy import pattern:

```python
from services.client_file_service import ensure_client_file
ensure_client_file(db, lead_variable_name)
```

Where `lead_variable_name` is the actual variable name used in each file (usually `lead`, `db_lead`, `new_lead`, etc.).

| # | File | Line | Variable name |
|---|---|---|---|
| 2 | `public_routes.py:1579` | after flush | Check actual var name |
| 3 | `vapi_routes.py:988` | after flush | Check actual var name |
| 4 | `vapi_routes.py:1135` | after flush | Check actual var name |
| 5 | `vapi_service.py:1104` | after flush | Check actual var name |
| 6 | `email_drop_routes.py:583` | after flush | Check actual var name |
| 7 | `microsite_routes.py:191` | after flush | Check actual var name |
| 8 | `routes/microsite_routes.py:740` | after flush | Check actual var name |
| 9 | `integrations/imessage/service.py:114` | after flush | Check actual var name |
| 10 | `routes/calendly_integration_routes.py:410` | after flush | Check actual var name |
| 11 | `routes/calendly_routes.py:856` | after flush | Check actual var name |
| 12 | `routes/conversation_intelligence_routes.py:389` | after flush | Check actual var name |
| 13 | `routes/data_reconciliation_routes.py:1020` | after flush | Check actual var name |
| 14 | `routes/data_reconciliation_routes.py:1816` | after flush | Check actual var name |
| 15 | `ai_command_screenshot_routes.py:199` | after flush | Check actual var name |
| 16 | `routes/chat_screenshot_routes.py:454` | after flush | Check actual var name |
| 17 | `routes/chat_screenshot_routes.py:671` | after flush | Check actual var name |
| 18 | `routes/internal/aria_tool_routes.py:288` | after flush | Check actual var name |
| 19 | `routes/mobile_api_routes.py:512` | after flush | Check actual var name |
| 20 | `routes/scheduler/_crm_integration.py:85` | after flush | Check actual var name |
| 21 | `routes/voice/telnyx_ws.py:338` | after flush | Check actual var name |
| 22 | `services/appointment_creation_service.py:533` | after flush | Check actual var name |
| 23 | `services/appointment/crm_bridge.py:49` | after flush | Check actual var name |
| 24 | `services/call_intelligence/process_transcript.py:582` | after flush | Check actual var name |
| 25 | `services/followupboss_sync_service.py:232` | after flush | Check actual var name |
| 26 | `services/partner_portal_service.py:317` | after flush | Check actual var name |
| 27 | `services/public_mortgage_chat_service.py:364` | after flush | Check actual var name |
| 28 | `services/vapi_scheduling_service.py:926` | after flush | Check actual var name |

For each file: open it, find the `Lead(` instantiation at the specified line, locate the `db.add()` + `db.flush()` or `db.commit()` call, and insert the hook. If the code uses `db.commit()` without a preceding `flush()`, add `db.flush()` before the hook, and keep `db.commit()` after.

**Pattern for files that use `db.commit()` directly (no flush):**
```python
db.add(lead)
db.flush()  # ← add this
from services.client_file_service import ensure_client_file
ensure_client_file(db, lead)
db.commit()  # existing
```

**If a 29th path is discovered during implementation, add it before committing.**

- [ ] **Step 4: Run the primary creation path test**

Run: `cd backend && python -m pytest tests/test_client_file_service.py tests/test_team_chat_routes.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A backend/routes/ backend/services/ backend/integrations/ backend/vapi_routes.py backend/vapi_service.py backend/email_drop_routes.py backend/microsite_routes.py backend/public_routes.py backend/ai_command_screenshot_routes.py
git commit -m "feat: hook ensure_client_file into all 28 lead creation paths + bridge endpoint"
```

---

## Task 10: Frontend — Copy Package Files + Add Route

**Files:**
- Create: `frontend/src/client-file/` (16 files from package)
- Create: `frontend/src/pages/ClientFilePage.jsx`
- Modify: `frontend/src/routes/index.jsx`
- Modify: `frontend/src/pages/LeadDetail.js`

- [ ] **Step 1: Copy the frontend package files**

```bash
cp -r /tmp/lo_surface/extracted/perennia_lo_surface/frontend/src/client-file frontend/src/
```

- [ ] **Step 2: Create the route wrapper page**

Create `frontend/src/pages/ClientFilePage.jsx`:

```jsx
import { useParams } from 'react-router-dom';
import { getCurrentUserId } from '../utils/auth';
import { ClientFileView } from '../client-file';

export default function ClientFilePage() {
  const { uuid } = useParams();
  const currentUserId = getCurrentUserId();

  if (!currentUserId) return null;

  return (
    <ClientFileView
      clientFileId={uuid}
      currentUserId={String(currentUserId)}
    />
  );
}
```

- [ ] **Step 3: Add route and lazy import in `routes/index.jsx`**

After line 120 (`const ClientProfile = lazyRetry(...)`) add:

```jsx
const ClientFilePage = lazyRetry(() => import('../pages/ClientFilePage'));
```

After line 605 (`<Route key="/leads/:id" ...>`) add:

```jsx
    <Route key="/clients/:uuid" path="/clients/:uuid" element={withMainLayout(ClientFilePage)} />,
```

- [ ] **Step 4: Add the API base URL configuration**

In `frontend/src/client-file/api.ts` (or wherever `setApiBaseUrl` is defined), check if the default base URL works for the Perennia setup. If the frontend calls `api.perenniaai.com`, ensure `setApiBaseUrl` is called at app startup.

Add to `frontend/src/App.jsx` in the imports section:

```jsx
import { setApiBaseUrl } from './client-file';
```

And at the top of the `App` function body (or in a useEffect):

```jsx
setApiBaseUrl(import.meta.env.VITE_API_URL || 'https://api.perenniaai.com/api/v1');
```

- [ ] **Step 5: Add stylesheet import**

In `frontend/src/App.jsx` (or `main.jsx`), add the CSS import:

```jsx
import './client-file/styles.css';
```

- [ ] **Step 6: Add "Open in Client File" link to LeadDetail**

In `frontend/src/pages/LeadDetail.js`, add a link/button that navigates to the client file view. Find a good location in the header area and add:

```jsx
import { useNavigate } from 'react-router-dom';
import { getAuthHeaders } from '../utils/auth';

// Inside the component, add a handler:
const handleOpenClientFile = async () => {
  try {
    const resp = await fetch(
      `${API_BASE}/api/v1/leads/${id}/client-file-id`,
      { headers: getAuthHeaders() }
    );
    if (resp.ok) {
      const data = await resp.json();
      navigate(`/clients/${data.client_file_id}`);
    }
  } catch (err) {
    console.error('Failed to resolve client file:', err);
  }
};

// Add a button in the header area:
<button onClick={handleOpenClientFile} className="btn-secondary">
  Open in Client File
</button>
```

- [ ] **Step 7: Start dev server and verify**

Run: `cd frontend && npm run dev`

Navigate to `/clients/<any-uuid>` and verify the 3-pane layout renders.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/client-file/ frontend/src/pages/ClientFilePage.jsx frontend/src/routes/index.jsx frontend/src/pages/LeadDetail.js frontend/src/App.jsx
git commit -m "feat: frontend — 3-pane client file view, team chat UI, /clients/:uuid route"
```

---

## Task 11: Final Integration Test + Verification

**Files:** No new files — this is a verification task.

- [ ] **Step 1: Run the full test suite**

Run: `cd backend && python -m pytest tests/test_client_file_service.py tests/test_client_file_model.py tests/test_team_chat_model.py tests/test_team_chat_service.py tests/test_team_chat_routes.py -v`

Expected: All tests PASS.

- [ ] **Step 2: Verify the migration applies cleanly**

Run: `cd backend && alembic upgrade --sql 014_client_file_and_team_chat > /tmp/014_verify.sql && wc -l /tmp/014_verify.sql`

Expected: SQL file generated with no errors.

- [ ] **Step 3: Verify the worker boots**

Run: `cd backend && timeout 5 python -c "from workers.team_chat_bot import main; print('Worker imports OK')" || true`

Expected: "Worker imports OK"

- [ ] **Step 4: Walk through the verification checklist from spec section 10**

Manually verify each item in the checklist. See the spec for the full list.

- [ ] **Step 5: Final commit with any remaining fixes**

```bash
git add -A
git commit -m "feat: client file aggregate root + team chat — integration verified"
```

---

## Deployment Sequence

After all tasks are merged:

1. **Deploy backend** with the new files
2. **Run migration**: `alembic upgrade head`
3. **Run backfill**: `python -m migrations.backfill_client_files`
4. **Verify backfill**: `SELECT COUNT(*) FROM client_files WHERE lead_id IS NOT NULL` = `SELECT COUNT(*) FROM leads`
5. **Start worker**: Deploy `team_chat_bot` Railway service
6. **Deploy frontend**
7. **Run verification checklist** (spec section 10)
