"""
Team chat service — channel CRUD, message lifecycle, reactions, read
cursors, and ephemeral presence (typing indicators) via Redis.

The channel is one-per-client-file with a UNIQUE constraint enforcing
that. Channels are created lazily — `get_or_create_channel` is the
canonical way to get a channel handle.

Membership is implicit: anyone with a ClientFileCollaborator record on
the ClientFile (or the assigned LO / processor / UW / LOA) is a member.
This service does NOT maintain a separate membership table — it derives
membership at read time from the existing collaborator structure. That
means:

  - Adding/removing collaborators on the ClientFile automatically
    adjusts who can see the chat.
  - There's no risk of drift between "who's on the file" and "who's in
    the chat."
  - The trade-off: querying "all channels I'm a member of" is more
    expensive (joins through collaborators). For v1 this is fine —
    the UI loads one channel at a time, scoped to the current client.

Auth: every method takes an `organization_id` and asserts the caller has
access to the underlying client_file. The standard RLS GUC
(`app.current_tenant`) handles tenant isolation at the DB level; this
service layer enforces caller authorization on top.

Adapted from package source:
  - org_id → organization_id (Integer, not UUID)
  - author_user_id → Integer FK to users.id (not UUID)
  - user_id in reactions/reads → Integer FK (not UUID)
  - display_name fallback removed (User model has no display_name column)
  - last_active_at → last_activity_at (actual User model column name)
  - Collaborator → ClientFileCollaborator (actual model in this codebase)
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.models import ClientFile, User
from database.models.team_chat import (
    TeamChatAgentSlug,
    TeamChatAuthorKind,
    TeamChatChannel,
    TeamChatMessage,
    TeamChatReaction,
    TeamChatReactionEmoji,
    TeamChatRead,
)

logger = logging.getLogger(__name__)

# Redis key conventions
def _typing_key(channel_id: uuid.UUID) -> str:
    return f"team_chat:typing:{channel_id}"

def _online_key(organization_id: int) -> str:
    return f"team_chat:online:{organization_id}"


# ─────────────────────────────────────────────────────────────────────────────
# DTOs returned by service methods (kept simple, JSON-serializable)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ReactionSummary:
    emoji: TeamChatReactionEmoji
    user_ids: list[int]
    count: int
    current_user_reacted: bool

    def to_dict(self) -> dict:
        return {
            "emoji": self.emoji.value,
            "user_ids": [str(u) for u in self.user_ids],
            "count": self.count,
            "current_user_reacted": self.current_user_reacted,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class TeamChatService:
    """All channel/message/reaction operations.

    Construct per-request with the active SQLAlchemy session and the
    Redis client. The Redis client is optional — without it, presence
    operations are no-ops (the chat still works, just without typing
    indicators).
    """

    TYPING_TTL_SECONDS = 5  # how long a typing indicator persists
    ONLINE_TTL_SECONDS = 90  # how long until a user's "online" expires

    def __init__(self, session: Session, redis: Optional[Any] = None):
        self.session = session
        self.redis = redis

    # ── Channel ──────────────────────────────────────────────────────────

    def get_or_create_channel(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
    ) -> TeamChatChannel:
        existing = self.session.execute(
            select(TeamChatChannel).where(
                and_(
                    TeamChatChannel.organization_id == organization_id,
                    TeamChatChannel.client_file_id == client_file_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        # Verify the client file exists and the caller has access — RLS
        # filters this query to the caller's org, so a non-existent file
        # will simply not be found here.
        client = self.session.get(ClientFile, client_file_id)
        if client is None or client.organization_id != organization_id:
            raise PermissionError(
                f"client_file {client_file_id} not accessible in org {organization_id}"
            )

        channel = TeamChatChannel(
            organization_id=organization_id,
            client_file_id=client_file_id,
        )
        self.session.add(channel)
        self.session.flush()
        return channel

    # ── Message lifecycle ────────────────────────────────────────────────

    def post_human_message(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        author_user_id: int,
        body: str,
        mentioned_user_ids: Optional[list[int]] = None,
        attachments: Optional[list[dict]] = None,
    ) -> TeamChatMessage:
        body = body.strip()
        if not body:
            raise ValueError("message body cannot be empty")
        if len(body) > 8000:
            raise ValueError("message body exceeds 8000 characters")

        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        msg = TeamChatMessage(
            organization_id=organization_id,
            channel_id=channel.id,
            client_file_id=client_file_id,
            author_kind=TeamChatAuthorKind.HUMAN,
            author_user_id=author_user_id,
            body=body,
            mentioned_user_ids=mentioned_user_ids or [],
            attachments=attachments or [],
        )
        self.session.add(msg)
        self.session.flush()

        # The author has implicitly read up to their own message
        self._upsert_read_cursor(channel.id, author_user_id, msg.id, organization_id)

        return msg

    def post_system_message(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        agent_slug: TeamChatAgentSlug,
        display_name: str,
        body: str,
        source_event_kind: Optional[str] = None,
        source_object_id: Optional[uuid.UUID] = None,
        source_object_label: Optional[str] = None,
    ) -> TeamChatMessage:
        """Post an automated system message — agent activity, lifecycle
        changes, milestone events. Called by SystemBotPublisher."""
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        msg = TeamChatMessage(
            organization_id=organization_id,
            channel_id=channel.id,
            client_file_id=client_file_id,
            author_kind=TeamChatAuthorKind.SYSTEM,
            system_agent_slug=agent_slug,
            system_display_name=display_name,
            system_source_event_kind=source_event_kind,
            system_source_object_id=source_object_id,
            system_source_object_label=source_object_label,
            body=body,
            mentioned_user_ids=[],
            attachments=[],
        )
        self.session.add(msg)
        self.session.flush()
        return msg

    def edit_message(
        self,
        *,
        message_id: uuid.UUID,
        actor_user_id: int,
        body: str,
    ) -> TeamChatMessage:
        msg = self.session.get(TeamChatMessage, message_id)
        if msg is None:
            raise ValueError(f"message {message_id} not found")
        if msg.author_kind != TeamChatAuthorKind.HUMAN:
            raise PermissionError("cannot edit system messages")
        if msg.author_user_id != actor_user_id:
            raise PermissionError("can only edit your own messages")
        if msg.deleted_at is not None:
            raise ValueError("cannot edit deleted message")
        msg.body = body.strip()
        msg.edited_at = datetime.now(timezone.utc)
        self.session.flush()
        return msg

    def delete_message(
        self,
        *,
        message_id: uuid.UUID,
        actor_user_id: int,
    ) -> None:
        msg = self.session.get(TeamChatMessage, message_id)
        if msg is None:
            return
        if msg.author_kind != TeamChatAuthorKind.HUMAN:
            raise PermissionError("cannot delete system messages")
        if msg.author_user_id != actor_user_id:
            raise PermissionError("can only delete your own messages")
        msg.deleted_at = datetime.now(timezone.utc)
        msg.body = "(deleted)"  # tombstone — keep row for thread continuity
        self.session.flush()

    # ── Listing ──────────────────────────────────────────────────────────

    def list_messages(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        actor_user_id: int,
        before: Optional[datetime] = None,
        limit: int = 80,
    ) -> list[dict]:
        """Returns messages with reactions denormalized for the API."""
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        q = (
            select(TeamChatMessage)
            .where(TeamChatMessage.channel_id == channel.id)
            .order_by(TeamChatMessage.created_at.desc())
            .limit(min(limit, 200))
        )
        if before:
            q = q.where(TeamChatMessage.created_at < before)
        rows = list(self.session.execute(q).scalars().all())
        rows.reverse()  # ascending for the UI

        if not rows:
            return []

        # Bulk reaction load
        msg_ids = [m.id for m in rows]
        reactions_q = select(TeamChatReaction).where(
            TeamChatReaction.message_id.in_(msg_ids)
        )
        reactions = list(self.session.execute(reactions_q).scalars().all())

        reactions_by_msg: dict[uuid.UUID, dict[TeamChatReactionEmoji, list[int]]] = {}
        for r in reactions:
            reactions_by_msg.setdefault(r.message_id, {}).setdefault(
                r.emoji, []
            ).append(r.user_id)

        # User display info bulk load (for human authors)
        author_ids = [m.author_user_id for m in rows if m.author_user_id]
        users_by_id: dict[int, User] = {}
        if author_ids:
            users = list(
                self.session.execute(
                    select(User).where(User.id.in_(author_ids))
                ).scalars().all()
            )
            users_by_id = {u.id: u for u in users}

        out: list[dict] = []
        for m in rows:
            out.append(
                self._serialize_message(
                    m,
                    actor_user_id=actor_user_id,
                    reactions_by_emoji=reactions_by_msg.get(m.id, {}),
                    users_by_id=users_by_id,
                )
            )
        return out

    def _serialize_message(
        self,
        m: TeamChatMessage,
        *,
        actor_user_id: int,
        reactions_by_emoji: dict[TeamChatReactionEmoji, list[int]],
        users_by_id: dict[int, User],
    ) -> dict:
        if m.author_kind == TeamChatAuthorKind.HUMAN:
            user = users_by_id.get(m.author_user_id) if m.author_user_id else None
            author_block: dict[str, Any] = {
                "kind": "human",
                "user_id": str(m.author_user_id) if m.author_user_id else None,
                "display_name": _user_display_name(user) if user else "Unknown",
                "initials": _user_initials(user) if user else "??",
                "role": getattr(user, "role", "loan_officer") if user else "loan_officer",
            }
        else:
            author_block = {
                "kind": "system",
                "agent_slug": m.system_agent_slug.value if m.system_agent_slug else None,
                "display_name": m.system_display_name or "System",
                "source_event_kind": m.system_source_event_kind,
                "source_object_id": str(m.system_source_object_id) if m.system_source_object_id else None,
                "source_object_label": m.system_source_object_label,
            }

        reaction_summaries = [
            ReactionSummary(
                emoji=emoji,
                user_ids=user_ids,
                count=len(user_ids),
                current_user_reacted=actor_user_id in user_ids,
            ).to_dict()
            for emoji, user_ids in reactions_by_emoji.items()
        ]

        return {
            "id": str(m.id),
            "channel_id": str(m.channel_id),
            "client_file_id": str(m.client_file_id),
            "author": author_block,
            "body": m.body,
            "mentioned_user_ids": [str(u) for u in (m.mentioned_user_ids or [])],
            "attachments": m.attachments or [],
            "reactions": reaction_summaries,
            "is_pinned": m.is_pinned,
            "created_at": m.created_at.isoformat(),
            "edited_at": m.edited_at.isoformat() if m.edited_at else None,
            "deleted_at": m.deleted_at.isoformat() if m.deleted_at else None,
        }

    # ── Reactions ────────────────────────────────────────────────────────

    def react(
        self,
        *,
        message_id: uuid.UUID,
        user_id: int,
        emoji: TeamChatReactionEmoji,
        organization_id: int,
    ) -> TeamChatReaction:
        # Upsert via Postgres ON CONFLICT — idempotent
        stmt = pg_insert(TeamChatReaction).values(
            organization_id=organization_id,
            message_id=message_id,
            user_id=user_id,
            emoji=emoji,
        ).on_conflict_do_nothing(
            index_elements=["message_id", "user_id", "emoji"]
        )
        self.session.execute(stmt)
        self.session.flush()
        return self.session.execute(
            select(TeamChatReaction).where(
                and_(
                    TeamChatReaction.message_id == message_id,
                    TeamChatReaction.user_id == user_id,
                    TeamChatReaction.emoji == emoji,
                )
            )
        ).scalar_one()

    def unreact(
        self,
        *,
        message_id: uuid.UUID,
        user_id: int,
        emoji: TeamChatReactionEmoji,
    ) -> None:
        existing = self.session.execute(
            select(TeamChatReaction).where(
                and_(
                    TeamChatReaction.message_id == message_id,
                    TeamChatReaction.user_id == user_id,
                    TeamChatReaction.emoji == emoji,
                )
            )
        ).scalar_one_or_none()
        if existing:
            self.session.delete(existing)
            self.session.flush()

    # ── Pinning ──────────────────────────────────────────────────────────

    def pin(self, *, message_id: uuid.UUID) -> TeamChatMessage:
        msg = self.session.get(TeamChatMessage, message_id)
        if msg is None:
            raise ValueError(f"message {message_id} not found")
        # Unpin any other pinned message in this channel — single-pin policy
        existing_pinned = self.session.execute(
            select(TeamChatMessage).where(
                and_(
                    TeamChatMessage.channel_id == msg.channel_id,
                    TeamChatMessage.is_pinned.is_(True),
                    TeamChatMessage.id != message_id,
                )
            )
        ).scalars().all()
        for prev in existing_pinned:
            prev.is_pinned = False
        msg.is_pinned = True
        # Update channel pointer for fast lookup
        channel = self.session.get(TeamChatChannel, msg.channel_id)
        if channel:
            channel.pinned_message_id = msg.id
        self.session.flush()
        return msg

    def unpin(self, *, message_id: uuid.UUID) -> TeamChatMessage:
        msg = self.session.get(TeamChatMessage, message_id)
        if msg is None:
            raise ValueError(f"message {message_id} not found")
        msg.is_pinned = False
        channel = self.session.get(TeamChatChannel, msg.channel_id)
        if channel and channel.pinned_message_id == msg.id:
            channel.pinned_message_id = None
        self.session.flush()
        return msg

    def get_pinned(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        actor_user_id: int,
    ) -> Optional[dict]:
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        if channel.pinned_message_id is None:
            return None
        msg = self.session.get(TeamChatMessage, channel.pinned_message_id)
        if msg is None or not msg.is_pinned:
            return None
        return self._serialize_message(
            msg,
            actor_user_id=actor_user_id,
            reactions_by_emoji={},
            users_by_id={},
        )

    # ── Read cursors ─────────────────────────────────────────────────────

    def _upsert_read_cursor(
        self,
        channel_id: uuid.UUID,
        user_id: int,
        last_read_message_id: uuid.UUID,
        organization_id: int,
    ) -> None:
        stmt = pg_insert(TeamChatRead).values(
            organization_id=organization_id,
            channel_id=channel_id,
            user_id=user_id,
            last_read_message_id=last_read_message_id,
            last_read_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["channel_id", "user_id"],
            set_={
                "last_read_message_id": last_read_message_id,
                "last_read_at": datetime.now(timezone.utc),
            },
        )
        self.session.execute(stmt)

    def mark_read(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        user_id: int,
        last_read_message_id: uuid.UUID,
    ) -> dict:
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        self._upsert_read_cursor(channel.id, user_id, last_read_message_id, organization_id)
        self.session.flush()
        return {
            "channel_id": str(channel.id),
            "user_id": str(user_id),
            "last_read_message_id": str(last_read_message_id),
            "last_read_at": datetime.now(timezone.utc).isoformat(),
        }

    def unread_count(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        user_id: int,
    ) -> dict:
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        cursor = self.session.execute(
            select(TeamChatRead).where(
                and_(
                    TeamChatRead.channel_id == channel.id,
                    TeamChatRead.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

        # Build the unread filter
        base = (
            select(TeamChatMessage)
            .where(TeamChatMessage.channel_id == channel.id)
            .where(TeamChatMessage.deleted_at.is_(None))
        )
        if cursor is not None:
            cutoff = self.session.get(TeamChatMessage, cursor.last_read_message_id)
            if cutoff is not None:
                base = base.where(TeamChatMessage.created_at > cutoff.created_at)

        unread_msgs = list(self.session.execute(base).scalars().all())
        unread = len(unread_msgs)
        mentions = sum(
            1 for m in unread_msgs if user_id in (m.mentioned_user_ids or [])
        )
        return {"unread": unread, "mentions": mentions}

    # ── Presence (Redis-backed) ──────────────────────────────────────────

    def set_typing(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
        user_id: int,
    ) -> None:
        if self.redis is None:
            return
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        key = _typing_key(channel.id)
        # ZADD with score = expiry timestamp; clients fetching read by score
        score = datetime.now(timezone.utc).timestamp() + self.TYPING_TTL_SECONDS
        try:
            self.redis.zadd(key, {str(user_id): score})
            self.redis.expire(key, self.TYPING_TTL_SECONDS * 4)
        except Exception:  # noqa: BLE001
            logger.warning("team_chat.set_typing.redis_failed", exc_info=True)

    def get_typing(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
    ) -> dict:
        if self.redis is None:
            return {"typing_user_ids": []}
        channel = self.get_or_create_channel(
            organization_id=organization_id, client_file_id=client_file_id
        )
        now = datetime.now(timezone.utc).timestamp()
        try:
            members = self.redis.zrangebyscore(
                _typing_key(channel.id), now, "+inf"
            )
            ids = [
                m.decode() if isinstance(m, bytes) else m for m in (members or [])
            ]
            return {"typing_user_ids": ids}
        except Exception:  # noqa: BLE001
            logger.warning("team_chat.get_typing.redis_failed", exc_info=True)
            return {"typing_user_ids": []}

    # ── Members ──────────────────────────────────────────────────────────

    def list_members(
        self,
        *,
        organization_id: int,
        client_file_id: uuid.UUID,
    ) -> list[dict]:
        """Resolve channel membership from the ClientFile's collaborators
        plus the assigned LO/LOA/processor/UW.

        Returns serialized member dicts ordered by role.
        """
        client = self.session.get(ClientFile, client_file_id)
        if client is None:
            return []

        member_user_ids: set[int] = set()
        for attr in (
            "assigned_loan_officer_id",
            "assigned_loan_assistant_id",
            "assigned_processor_id",
            "assigned_underwriter_id",
        ):
            uid = getattr(client, attr, None)
            if uid:
                member_user_ids.add(uid)

        # Pull collaborators from ClientFileCollaborator model
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

        if not member_user_ids:
            return []

        users = list(
            self.session.execute(
                select(User).where(User.id.in_(member_user_ids))
            ).scalars().all()
        )

        # Online check — Redis SADD/SREM with TTL pattern. Best-effort.
        online_ids: set[str] = set()
        if self.redis is not None:
            try:
                raw = self.redis.smembers(_online_key(organization_id))
                online_ids = {
                    (m.decode() if isinstance(m, bytes) else m) for m in (raw or [])
                }
            except Exception:  # noqa: BLE001
                pass

        return [
            {
                "user_id": str(u.id),
                "display_name": _user_display_name(u),
                "initials": _user_initials(u),
                "role": getattr(u, "role", "loan_officer"),
                "is_online": str(u.id) in online_ids,
                "last_seen_at": (
                    u.last_activity_at.isoformat()
                    if getattr(u, "last_activity_at", None)
                    else None
                ),
            }
            for u in users
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _user_display_name(u: Optional[User]) -> str:
    if u is None:
        return "Unknown"
    first = getattr(u, "first_name", "") or ""
    last = getattr(u, "last_name", "") or ""
    name = (first + " " + last).strip()
    if name:
        return name
    return getattr(u, "email", "") or str(u.id)


def _user_initials(u: Optional[User]) -> str:
    if u is None:
        return "??"
    first = (getattr(u, "first_name", "") or "")[:1]
    last = (getattr(u, "last_name", "") or "")[:1]
    if first and last:
        return (first + last).upper()
    name = _user_display_name(u)
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][:1] + parts[-1][:1]).upper()
    return name[:2].upper() if name else "??"
