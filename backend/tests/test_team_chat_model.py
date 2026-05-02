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
