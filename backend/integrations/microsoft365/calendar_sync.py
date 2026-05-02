"""Bi-directional calendar sync between the CRM and Outlook.

Loop prevention: when we write to Graph, we record the returned change_key.
When a notification arrives, we compare — if equal, we skip (self-triggered).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .graph_client import GraphAPIError, GraphClient
from .models import MSAccount, MSCalendarSyncMapping
from .schemas import CRMEventUpsert

log = logging.getLogger(__name__)


async def push_crm_event_to_outlook(
    db: Session,
    account: MSAccount,
    event: CRMEventUpsert,
) -> MSCalendarSyncMapping:
    payload = _build_graph_event_payload(event)
    payload_hash = _hash_payload(payload)

    mapping = db.query(MSCalendarSyncMapping).filter(
        MSCalendarSyncMapping.organization_id == account.organization_id,
        MSCalendarSyncMapping.crm_event_id == event.crm_event_id,
    ).first()

    async with GraphClient(db, account) as gc:
        if mapping is None:
            graph_event = await gc.post("/me/events", json=payload)
            mapping = MSCalendarSyncMapping(
                organization_id=account.organization_id,
                ms_account_id=account.id,
                crm_event_id=event.crm_event_id,
                graph_event_id=graph_event["id"],
                graph_etag=graph_event.get("@odata.etag"),
                graph_change_key=graph_event.get("changeKey"),
                direction="crm_to_outlook",
                last_synced_payload_hash=payload_hash,
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(mapping)
            db.flush()
        else:
            if mapping.last_synced_payload_hash == payload_hash:
                return mapping
            try:
                graph_event = await gc.patch(
                    f"/me/events/{mapping.graph_event_id}", json=payload
                )
            except GraphAPIError as exc:
                if exc.status == 404:
                    graph_event = await gc.post("/me/events", json=payload)
                    mapping.graph_event_id = graph_event["id"]
                else:
                    raise
            mapping.graph_etag = graph_event.get("@odata.etag")
            mapping.graph_change_key = graph_event.get("changeKey")
            mapping.last_synced_payload_hash = payload_hash
            mapping.last_synced_at = datetime.now(timezone.utc)
            db.flush()

    return mapping


async def delete_crm_event_in_outlook(
    db: Session, account: MSAccount, crm_event_id: int
) -> None:
    mapping = db.query(MSCalendarSyncMapping).filter(
        MSCalendarSyncMapping.organization_id == account.organization_id,
        MSCalendarSyncMapping.crm_event_id == crm_event_id,
    ).first()
    if not mapping:
        return

    async with GraphClient(db, account) as gc:
        try:
            await gc.delete(f"/me/events/{mapping.graph_event_id}")
        except GraphAPIError as exc:
            if exc.status != 404:
                raise

    mapping.is_deleted = True
    db.flush()


async def pull_outlook_event_into_crm(
    db: Session, account: MSAccount, graph_event_id: str
) -> dict[str, Any] | None:
    async with GraphClient(db, account) as gc:
        try:
            graph_event = await gc.get(f"/me/events/{graph_event_id}")
        except GraphAPIError as exc:
            if exc.status == 404:
                _mark_mapping_deleted_by_graph_id(db, account, graph_event_id)
                return None
            raise

    incoming_change_key = graph_event.get("changeKey")
    mapping = db.query(MSCalendarSyncMapping).filter(
        MSCalendarSyncMapping.ms_account_id == account.id,
        MSCalendarSyncMapping.graph_event_id == graph_event_id,
    ).first()

    if mapping and incoming_change_key and mapping.graph_change_key == incoming_change_key:
        log.debug("Skipping self-triggered calendar notification for %s", graph_event_id)
        return None

    crm_payload = _normalize_graph_event(graph_event)

    if mapping is None:
        crm_event_id = _create_crm_event(account, crm_payload)
        mapping = MSCalendarSyncMapping(
            organization_id=account.organization_id,
            ms_account_id=account.id,
            crm_event_id=crm_event_id,
            graph_event_id=graph_event_id,
            graph_etag=graph_event.get("@odata.etag"),
            graph_change_key=incoming_change_key,
            direction="outlook_to_crm",
            last_synced_payload_hash=_hash_payload(_build_graph_event_payload_from_crm(crm_payload)),
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(mapping)
        db.flush()
    else:
        _update_crm_event(account, mapping.crm_event_id, crm_payload)
        mapping.graph_change_key = incoming_change_key
        mapping.graph_etag = graph_event.get("@odata.etag")
        mapping.last_synced_at = datetime.now(timezone.utc)
        db.flush()

    return crm_payload


def _build_graph_event_payload(event: CRMEventUpsert) -> dict[str, Any]:
    return {
        "subject": event.title,
        "body": {
            "contentType": "HTML",
            "content": event.body_html or "",
        },
        "start": {
            "dateTime": event.start.isoformat(),
            "timeZone": event.timezone,
        },
        "end": {
            "dateTime": event.end.isoformat(),
            "timeZone": event.timezone,
        },
        "location": {"displayName": event.location} if event.location else None,
        "attendees": [
            {
                "emailAddress": {"address": email},
                "type": "required",
            }
            for email in event.attendees
        ],
        "isOnlineMeeting": event.is_online_meeting,
        "onlineMeetingProvider": "teamsForBusiness" if event.is_online_meeting else None,
    }


def _build_graph_event_payload_from_crm(crm_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": crm_payload["title"],
        "body": {"contentType": "HTML", "content": crm_payload.get("body_html") or ""},
        "start": {
            "dateTime": crm_payload["start"].isoformat() if isinstance(crm_payload["start"], datetime) else crm_payload["start"],
            "timeZone": crm_payload.get("timezone", "UTC"),
        },
        "end": {
            "dateTime": crm_payload["end"].isoformat() if isinstance(crm_payload["end"], datetime) else crm_payload["end"],
            "timeZone": crm_payload.get("timezone", "UTC"),
        },
        "location": {"displayName": crm_payload["location"]} if crm_payload.get("location") else None,
        "attendees": [
            {"emailAddress": {"address": e}, "type": "required"}
            for e in crm_payload.get("attendees", [])
        ],
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _normalize_graph_event(graph_event: dict[str, Any]) -> dict[str, Any]:
    start = (graph_event.get("start") or {}).get("dateTime")
    end = (graph_event.get("end") or {}).get("dateTime")
    tz = (graph_event.get("start") or {}).get("timeZone", "UTC")
    return {
        "title": graph_event.get("subject") or "(no title)",
        "body_html": (graph_event.get("body") or {}).get("content"),
        "start": _parse_dt(start),
        "end": _parse_dt(end),
        "timezone": tz,
        "location": (graph_event.get("location") or {}).get("displayName"),
        "attendees": [
            (a.get("emailAddress") or {}).get("address", "").lower()
            for a in graph_event.get("attendees", [])
            if (a.get("emailAddress") or {}).get("address")
        ],
        "is_online_meeting": bool(graph_event.get("isOnlineMeeting")),
        "online_meeting_url": (graph_event.get("onlineMeeting") or {}).get("joinUrl"),
    }


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if "+" not in value and "-" not in value[10:]:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value)


def _mark_mapping_deleted_by_graph_id(
    db: Session, account: MSAccount, graph_event_id: str
) -> None:
    mapping = db.query(MSCalendarSyncMapping).filter(
        MSCalendarSyncMapping.ms_account_id == account.id,
        MSCalendarSyncMapping.graph_event_id == graph_event_id,
    ).first()
    if mapping:
        mapping.is_deleted = True
        db.flush()
        _delete_crm_event(account, mapping.crm_event_id)


# ── CRM calendar service hooks (wire to your existing service layer) ─────

def _create_crm_event(account: MSAccount, payload: dict[str, Any]) -> int:
    # TODO: Wire into Smart Calendar service
    # from services.smart_scheduler import create_event
    # return create_event(user_id=account.user_id, **payload)
    raise NotImplementedError(
        "Wire _create_crm_event to your calendar service before enabling Outlook->CRM sync"
    )


def _update_crm_event(account: MSAccount, crm_event_id: int, payload: dict[str, Any]) -> None:
    # TODO: Wire into Smart Calendar service
    pass


def _delete_crm_event(account: MSAccount, crm_event_id: int) -> None:
    # TODO: Wire into Smart Calendar service
    pass
