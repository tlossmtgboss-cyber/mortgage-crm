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
