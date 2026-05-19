"""Ingest a Microsoft Graph callRecord and push caller info to the CRM lightbox.

When a callRecord notification arrives, we fetch the full record from Graph
to extract participant phone numbers, then look up the caller in the CRM
and push a real-time notification to the target user via WebSocket.

Graph callRecords API reference:
  GET /communications/callRecords/{id}?$expand=sessions($expand=segments)
  Requires: CallRecords.Read.All (application permission)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .graph_client import GraphClient
from .models import MSAccount

log = logging.getLogger(__name__)


async def ingest_call_record(
    db: Session,
    account: MSAccount,
    record_id: str,
) -> None:
    """Fetch a callRecord and push inbound call info to the CRM lightbox."""
    try:
        async with GraphClient(db, account) as gc:
            record = await gc.get(
                f"/communications/callRecords/{record_id}",
                params={"$expand": "sessions($expand=segments)"},
            )
    except Exception as _exc:  # noqa: BLE001
        log.exception("Failed to fetch callRecord %s", record_id)
        return

    if not record:
        return

    call_type = record.get("type", "")
    if call_type not in ("unknown", "groupCall", "peerToPeer", ""):
        return

    participants = record.get("participants", [])
    organizer = record.get("organizer", {})

    caller_phone = ""
    caller_name = ""
    target_user_ms_id = ""

    for p in participants:
        user_info = p.get("user", {})
        phone_info = p.get("phone", {})

        if phone_info.get("id"):
            caller_phone = phone_info["id"]
            caller_name = phone_info.get("displayName", "")
        elif not user_info.get("id"):
            caller_phone = p.get("id", "")
            caller_name = p.get("displayName", "")

        if user_info.get("id") and user_info["id"] != organizer.get("user", {}).get("id"):
            target_user_ms_id = user_info["id"]

    if not target_user_ms_id:
        org_user = organizer.get("user", {})
        if org_user.get("id"):
            target_user_ms_id = org_user["id"]

    if not target_user_ms_id:
        log.debug("callRecord %s: no target user found", record_id)
        return

    from sqlalchemy import text

    user_row = db.execute(
        text("""
            SELECT u.id, u.organization_id
            FROM users u
            JOIN ms_accounts ma ON ma.user_id = u.id
            WHERE ma.ms_user_id = :ms_id AND ma.organization_id = :org_id
            LIMIT 1
        """),
        {"ms_id": target_user_ms_id, "org_id": account.organization_id},
    ).fetchone()

    if not user_row:
        log.debug("callRecord %s: no CRM user for ms_user_id=%s", record_id, target_user_ms_id)
        return

    target_user_id = user_row[0]
    org_id = user_row[1]

    if not caller_phone:
        for session in record.get("sessions", []):
            caller_ep = session.get("caller", {})
            phone_info = caller_ep.get("phone", {}) or caller_ep.get("userAgent", {})
            if phone_info.get("id"):
                caller_phone = phone_info["id"]
                caller_name = caller_name or phone_info.get("displayName", "")
                break

    contact = None
    if caller_phone:
        from routes.teams_call_routes import _lookup_contact_by_phone
        contact = _lookup_contact_by_phone(db, caller_phone, org_id)

    from routes.teams_call_routes import call_manager

    payload = {
        "type": "inbound_call",
        "caller_phone": caller_phone,
        "caller_display_name": caller_name,
        "call_id": record_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contact": contact,
    }

    await call_manager.notify_user(target_user_id, payload)
    log.info(
        "callRecord %s: pushed notification to user=%s phone=%s contact=%s",
        record_id, target_user_id, caller_phone, contact.get("name") if contact else None,
    )
