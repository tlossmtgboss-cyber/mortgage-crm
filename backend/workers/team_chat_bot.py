"""
System bot publisher — subscribes to the agent / lifecycle / milestone /
document event streams and posts summaries into each affected client
file's team chat channel.

This is what makes the team chat feel "alive" with autonomous activity:
when Cadence sends an SMS, when a document gets uploaded, when a
milestone changes — the team sees it inline in their chat.

Event sources subscribed (Redis Streams, consumer group `team_chat_bot`):

  perennia:cadence_events       → cadence_attempt_sent, sequence_won, etc.
  perennia:document_events      → document_uploaded, document_rejected
  perennia:milestone_events     → milestone_reached, milestone_at_risk
  perennia:client_file_events   → lifecycle_stage_changed
  perennia:agent_events         → insight_refreshed (high-confidence only)

Each event handler maps the event payload into a TeamChatService call
that posts a system message. Failures are logged but never block the
event stream — a chat post is "best effort," not part of the critical
path of any agent operation.

Run as: `python -m workers.team_chat_bot`
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from db import SessionLocal
from database.models.team_chat import TeamChatAgentSlug
from services.team_chat import TeamChatService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Event → message mappers
#
# Each mapper takes a raw event dict (from the bus) and returns a tuple of:
#   (org_id, client_file_id, agent_slug, display_name, body,
#    source_event_kind, source_object_id, source_object_label)
# or None if the event shouldn't post to chat (e.g. low-confidence insight).
# ─────────────────────────────────────────────────────────────────────────────


def _cadence_attempt_sent(event: dict) -> tuple | None:
    org_id = int(event["org_id"])
    client_file_id = uuid.UUID(event["client_file_id"])
    skill = event.get("skill_name", "follow-up")
    skill_version = event.get("skill_version", "")
    channel = event.get("channel", "sms")
    body_preview = event.get("body_preview", "")
    snippet = (body_preview[:80] + "…") if len(body_preview) > 80 else body_preview
    label = f"{skill} {skill_version}".strip()
    body = f'sent {channel.upper()} · "{snippet}"' if snippet else f"sent {channel.upper()}"
    return (
        org_id,
        client_file_id,
        TeamChatAgentSlug.CADENCE,
        "Cadence Agent",
        body,
        "cadence_attempt_sent",
        uuid.UUID(event["attempt_id"]) if event.get("attempt_id") else None,
        label,
    )


def _cadence_sequence_won(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.CADENCE,
        "Cadence Agent",
        f"sequence won — borrower {event.get('stop_reason', 'replied')}",
        "cadence_sequence_won",
        uuid.UUID(event["sequence_id"]) if event.get("sequence_id") else None,
        event.get("goal", "follow-up"),
    )


def _cadence_attempt_blocked(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.CADENCE,
        "Cadence Agent",
        f"compliance blocked send — {event.get('reason', 'see audit')}",
        "cadence_attempt_blocked",
        uuid.UUID(event["attempt_id"]) if event.get("attempt_id") else None,
        event.get("skill_name"),
    )


def _document_uploaded(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.DOCUMENT,
        "Document Agent",
        f"document uploaded by {event.get('uploaded_by_name', 'borrower')}",
        "document_uploaded",
        uuid.UUID(event["document_request_id"]) if event.get("document_request_id") else None,
        event.get("doc_title", "document"),
    )


def _document_rejected(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.DOCUMENT,
        "Document Agent",
        f"document flagged: {event.get('reason', 'review needed')}",
        "document_rejected",
        uuid.UUID(event["document_request_id"]) if event.get("document_request_id") else None,
        event.get("doc_title", "document"),
    )


def _milestone_reached(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.MILESTONE,
        "Milestone Engine",
        f"milestone reached: {event.get('milestone_label', 'milestone')}",
        "milestone_reached",
        None,
        event.get("milestone_label"),
    )


def _milestone_at_risk(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.MILESTONE,
        "Milestone Engine",
        f"⚠ milestone at risk: {event.get('milestone_label', '')} — {event.get('risk_reason', '')}",
        "milestone_at_risk",
        None,
        event.get("milestone_label"),
    )


def _lifecycle_changed(event: dict) -> tuple | None:
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.LIFECYCLE,
        "Lifecycle",
        f"stage moved {event.get('from_stage', '?')} → {event.get('to_stage', '?')}",
        "lifecycle_stage_changed",
        None,
        event.get("to_stage"),
    )


def _insight_refreshed(event: dict) -> tuple | None:
    # Only post if the engagement score moved significantly OR a new risk signal fired
    score_delta = event.get("score_delta", 0)
    new_risks = event.get("new_risk_signals", [])
    if abs(score_delta) < 10 and not new_risks:
        return None
    parts = []
    if abs(score_delta) >= 10:
        direction = "↑" if score_delta > 0 else "↓"
        parts.append(f"engagement {direction}{abs(score_delta)}pts")
    if new_risks:
        parts.append("new risk: " + ", ".join(new_risks))
    return (
        int(event["org_id"]),
        uuid.UUID(event["client_file_id"]),
        TeamChatAgentSlug.INSIGHT,
        "Insight Agent",
        " · ".join(parts),
        "insight_refreshed",
        None,
        None,
    )


EVENT_HANDLERS: dict[str, Callable[[dict], tuple | None]] = {
    "cadence_attempt_sent": _cadence_attempt_sent,
    "cadence_sequence_won": _cadence_sequence_won,
    "cadence_attempt_blocked": _cadence_attempt_blocked,
    "document_uploaded": _document_uploaded,
    "document_rejected": _document_rejected,
    "milestone_reached": _milestone_reached,
    "milestone_at_risk": _milestone_at_risk,
    "lifecycle_stage_changed": _lifecycle_changed,
    "insight_refreshed": _insight_refreshed,
}

STREAMS = [
    "perennia:cadence_events",
    "perennia:document_events",
    "perennia:milestone_events",
    "perennia:client_file_events",
    "perennia:agent_events",
]
CONSUMER_GROUP = "team_chat_bot"
CONSUMER_NAME_PREFIX = "team_chat_bot"


# ─────────────────────────────────────────────────────────────────────────────
# Worker loop
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def _scoped_session() -> Iterator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_consumer_groups(redis: Any) -> None:
    for stream in STREAMS:
        try:
            redis.xgroup_create(stream, CONSUMER_GROUP, id="$", mkstream=True)
        except Exception as e:  # noqa: BLE001
            # BUSYGROUP is expected on restart
            if "BUSYGROUP" not in str(e):
                logger.warning(
                    "team_chat_bot.xgroup_create_failed",
                    extra={"stream": stream, "error": str(e)},
                )


def _process_event(redis: Any, stream: str, event_id: str, fields: dict) -> None:
    payload_raw = fields.get(b"payload") or fields.get("payload")
    if not payload_raw:
        return
    if isinstance(payload_raw, bytes):
        payload_raw = payload_raw.decode()
    try:
        event = json.loads(payload_raw)
    except json.JSONDecodeError:
        logger.warning(
            "team_chat_bot.bad_payload",
            extra={"stream": stream, "event_id": event_id},
        )
        return

    # Bridge resolution: if event arrived with lead_id but no client_file_id,
    # look up the ClientFile by lead_id.
    if "client_file_id" not in event and "lead_id" in event:
        with _scoped_session() as session:
            from sqlalchemy import select
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

    event_kind = event.get("kind") or event.get("event_kind")
    handler = EVENT_HANDLERS.get(event_kind)
    if handler is None:
        return

    try:
        result = handler(event)
    except Exception:  # noqa: BLE001
        logger.exception(
            "team_chat_bot.handler_failed",
            extra={"stream": stream, "kind": event_kind},
        )
        return

    if result is None:
        return  # handler chose to skip (e.g. low-confidence insight)

    (
        org_id,
        client_file_id,
        agent_slug,
        display_name,
        body,
        source_event_kind,
        source_object_id,
        source_object_label,
    ) = result

    try:
        with _scoped_session() as session:
            svc = TeamChatService(session, redis=redis)
            svc.post_system_message(
                organization_id=org_id,
                client_file_id=client_file_id,
                agent_slug=agent_slug,
                display_name=display_name,
                body=body,
                source_event_kind=source_event_kind,
                source_object_id=source_object_id,
                source_object_label=source_object_label,
            )
    except Exception:  # noqa: BLE001
        logger.exception(
            "team_chat_bot.post_failed",
            extra={
                "stream": stream,
                "kind": event_kind,
                "client_file_id": str(client_file_id),
            },
        )


def run_worker_loop(redis: Any, consumer_id: str = "0") -> None:
    """Run forever, consuming agent events and posting to team chats."""
    _ensure_consumer_groups(redis)
    consumer_name = f"{CONSUMER_NAME_PREFIX}_{consumer_id}"
    streams_dict = {s: ">" for s in STREAMS}
    logger.info("team_chat_bot.starting", extra={"consumer": consumer_name})

    while True:
        try:
            results = redis.xreadgroup(
                CONSUMER_GROUP,
                consumer_name,
                streams_dict,
                count=20,
                block=5000,
            )
        except Exception:  # noqa: BLE001
            logger.exception("team_chat_bot.xreadgroup_failed")
            time.sleep(1)
            continue

        if not results:
            continue

        for stream_name, entries in results:
            stream_str = (
                stream_name.decode() if isinstance(stream_name, bytes) else stream_name
            )
            for event_id, fields in entries:
                event_id_str = (
                    event_id.decode() if isinstance(event_id, bytes) else event_id
                )
                try:
                    _process_event(redis, stream_str, event_id_str, fields)
                finally:
                    redis.xack(stream_str, CONSUMER_GROUP, event_id_str)


def main() -> None:
    import os

    logging.basicConfig(level=logging.INFO)
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    from services.redis_service import get_redis_client
    redis_client = get_redis_client()
    if redis_client is None:
        import redis as redis_lib
        redis_client = redis_lib.from_url(redis_url)
    consumer_id = os.environ.get("HOSTNAME", "local")
    run_worker_loop(redis_client, consumer_id=consumer_id)


if __name__ == "__main__":
    main()
