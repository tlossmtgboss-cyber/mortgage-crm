"""
Team chat — per-client-file internal coordination channel.

Schema is intentionally minimal:

  team_chat_channels  ──── one row per ClientFile (UNIQUE constraint)
  team_chat_messages  ──── messages sent into a channel; can be from a
                           human user OR a system bot (agent / lifecycle /
                           milestone events). Author kind is discriminated
                           by `author_kind` ('human' | 'system').
  team_chat_reactions ──── one row per (message, user, emoji); aggregated
                           into reaction summaries at read time.
  team_chat_reads     ──── per-user read cursor per channel (for unread
                           counts and notification badges).

Realtime presence (typing indicators, who's online) is NOT persisted —
that lives in Redis under per-channel keys with TTLs.

Adaptation notes (from package source):
  - org_id → organization_id (Integer, not UUID; RLS handles isolation)
  - author_user_id → Integer FK to users.id (not UUID)
  - user_id in reactions/reads → Integer FK (not UUID)
  - mentioned_user_ids → ARRAY(Integer) (not ARRAY(UUID))
  - UUID PKs and UUID cross-refs (channel_id, client_file_id, etc.) unchanged
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class TeamChatAuthorKind(str, enum.Enum):
    HUMAN = "human"
    SYSTEM = "system"


class TeamChatAgentSlug(str, enum.Enum):
    """Identifies which agent / system component posted a system message."""

    CADENCE = "cadence"
    ARIA = "aria"
    AVERY = "avery"
    INSIGHT = "insight"
    OPS_MANAGER = "ops_manager"
    DOCUMENT = "document"
    MILESTONE = "milestone"
    LIFECYCLE = "lifecycle"


class TeamChatReactionEmoji(str, enum.Enum):
    """Curated set — keeping it small drives consistent semantics.

    thumbs_up = "I see this / agree"
    check     = "Done / confirmed"
    fire      = "Important / urgent"
    question  = "Need clarification"
    """

    THUMBS_UP = "thumbs_up"
    CHECK = "check"
    FIRE = "fire"
    QUESTION = "question"


# ─────────────────────────────────────────────────────────────────────────────
# Channel — one per client file
# ─────────────────────────────────────────────────────────────────────────────


class TeamChatChannel(Base):
    """One channel per client file. Created lazily on first message access."""

    __tablename__ = "team_chat_channels"
    __table_args__ = (
        UniqueConstraint(
            "client_file_id", name="uq_team_chat_channels_client_file"
        ),
        Index("ix_team_chat_channels_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    client_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    pinned_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list["TeamChatMessage"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
        primaryjoin="TeamChatChannel.id==TeamChatMessage.channel_id",
        order_by="TeamChatMessage.created_at",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────────────────────


class TeamChatMessage(Base):
    """A message in a team chat channel.

    `author_kind` = 'human'  →  `author_user_id` is set, system_* fields null
    `author_kind` = 'system' →  `author_user_id` null, system_* fields set

    The system fields capture the agent slug, display name, and a back-
    reference to the source object (e.g. the cadence_attempt_id whose
    successful send triggered this message). Click-through in the UI uses
    `system_source_object_id` + the slug to route to the right detail view.
    """

    __tablename__ = "team_chat_messages"
    __table_args__ = (
        Index("ix_team_chat_messages_channel_time",
              "channel_id", "created_at"),
        Index("ix_team_chat_messages_org", "organization_id"),
        Index("ix_team_chat_messages_client_file", "client_file_id"),
        Index(
            "ix_team_chat_messages_mentions",
            "mentioned_user_ids",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_chat_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    author_kind: Mapped[TeamChatAuthorKind] = mapped_column(
        SAEnum(TeamChatAuthorKind, name="team_chat_author_kind"),
        nullable=False,
    )
    # Set when author_kind = HUMAN
    author_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set when author_kind = SYSTEM
    system_agent_slug: Mapped[Optional[TeamChatAgentSlug]] = mapped_column(
        SAEnum(TeamChatAgentSlug, name="team_chat_agent_slug"),
        nullable=True,
    )
    system_display_name: Mapped[Optional[str]] = mapped_column(String(80))
    system_source_event_kind: Mapped[Optional[str]] = mapped_column(String(80))
    system_source_object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True)
    )
    system_source_object_label: Mapped[Optional[str]] = mapped_column(String(200))

    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentioned_user_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{}"
    )
    attachments: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    channel: Mapped["TeamChatChannel"] = relationship(
        back_populates="messages",
        primaryjoin="TeamChatMessage.channel_id==TeamChatChannel.id",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Reactions
# ─────────────────────────────────────────────────────────────────────────────


class TeamChatReaction(Base):
    __tablename__ = "team_chat_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "emoji",
            name="uq_team_chat_reactions_msg_user_emoji",
        ),
        Index("ix_team_chat_reactions_message", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji: Mapped[TeamChatReactionEmoji] = mapped_column(
        SAEnum(TeamChatReactionEmoji, name="team_chat_reaction_emoji"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Read cursors — for unread counts and notifications
# ─────────────────────────────────────────────────────────────────────────────


class TeamChatRead(Base):
    """One row per (channel, user). Tracks how far the user has read."""

    __tablename__ = "team_chat_reads"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "user_id",
            name="uq_team_chat_reads_channel_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_chat_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_read_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
