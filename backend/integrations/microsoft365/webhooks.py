"""Inbound Microsoft Graph webhook handler.

Graph posts JSON envelopes of change notifications to our public URL.
We respond to validation handshakes, verify clientState, and dispatch
to the correct ingestion function.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from .models import MSAccount, MSGraphSubscription, SubscriptionKind
from .schemas import GraphNotificationBatch
from .subscriptions import verify_client_state

from db import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["microsoft-webhooks"])


@router.post("/webhooks/{kind}")
async def handle_webhook(
    kind: str,
    request: Request,
    db: Session = Depends(get_db),
    validation_token: Annotated[str | None, Query(alias="validationToken")] = None,
) -> Response:
    if validation_token is not None:
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    valid_kinds = {k.value for k in SubscriptionKind}
    if kind not in valid_kinds:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown subscription kind")

    try:
        body = await request.json()
        batch = GraphNotificationBatch.model_validate(body)
    except Exception as _exc:  # noqa: BLE001
        log.exception("Invalid webhook body")
        return Response(status_code=202)

    accepted = 0
    for notification in batch.value:
        sub = db.query(MSGraphSubscription).filter(
            MSGraphSubscription.graph_subscription_id == notification.subscription_id
        ).first()
        if not sub:
            log.warning("Notification for unknown subscription %s", notification.subscription_id)
            continue

        if not notification.client_state or not verify_client_state(
            notification.client_state, sub.ms_account_id, sub.kind
        ):
            log.warning(
                "Notification %s failed clientState verification",
                notification.subscription_id,
            )
            continue

        account = db.query(MSAccount).get(sub.ms_account_id)
        if not account or not account.is_active:
            continue

        asyncio.create_task(
            _dispatch_notification(
                kind, account.id, notification.resource_data or {}, notification.change_type
            )
        )
        accepted += 1

    log.info("Webhook[%s]: accepted=%s of %s", kind, accepted, len(batch.value))
    return Response(status_code=202)


async def _dispatch_notification(
    kind: str,
    account_id: int,
    resource_data: dict,
    change_type: str,
) -> None:
    from db import SessionLocal

    try:
        db = SessionLocal()
        try:
            account = db.query(MSAccount).get(account_id)
            if not account or not account.is_active:
                return

            if kind == SubscriptionKind.EMAIL.value:
                from .email_ingest import ingest_message
                msg_id = resource_data.get("id")
                if msg_id and change_type in ("created", "updated"):
                    await ingest_message(db, account, msg_id)

            elif kind == SubscriptionKind.CALENDAR.value:
                from .calendar_sync import pull_outlook_event_into_crm, _mark_mapping_deleted_by_graph_id
                event_id = resource_data.get("id")
                if not event_id:
                    return
                if change_type == "deleted":
                    _mark_mapping_deleted_by_graph_id(db, account, event_id)
                else:
                    await pull_outlook_event_into_crm(db, account, event_id)

            elif kind == SubscriptionKind.TEAMS_CHATS.value:
                from .teams_ingest import ingest_chat_message
                chat_id, message_id = _parse_teams_resource(resource_data)
                if chat_id and message_id and change_type == "created":
                    await ingest_chat_message(
                        db, account, chat_id=chat_id, message_id=message_id
                    )

            elif kind == SubscriptionKind.CALL_RECORDS.value:
                from .call_record_ingest import ingest_call_record
                record_id = resource_data.get("id")
                if record_id and change_type == "created":
                    await ingest_call_record(db, account, record_id)

            db.commit()
        finally:
            db.close()
    except Exception as _exc:  # noqa: BLE001
        log.exception("Notification dispatch failed (kind=%s)", kind)


def _parse_teams_resource(resource_data: dict) -> tuple[str | None, str | None]:
    message_id = resource_data.get("id")
    chat_id = resource_data.get("chatId")
    if chat_id and message_id:
        return chat_id, message_id
    odata_id = resource_data.get("@odata.id") or ""
    import re
    m = re.search(r"chats\('([^']+)'\)/messages\('([^']+)'\)", odata_id)
    if m:
        return m.group(1), m.group(2)
    return None, None
