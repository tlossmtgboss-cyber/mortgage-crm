"""Inbound email ingestion.

Webhook handler delegates to ingest_message, which fetches the full message
from Graph, stores it (idempotent on internet_message_id), runs reconciliation,
and persists the result.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .graph_client import GraphClient
from .models import MSAccount, MSEmailReconciliation, ReconciliationStatus
from .reconciliation import reconcile_email

log = logging.getLogger(__name__)


async def ingest_message(
    db: Session, account: MSAccount, graph_message_id: str
) -> MSEmailReconciliation | None:
    async with GraphClient(db, account) as gc:
        try:
            msg = await gc.get(
                f"/me/messages/{graph_message_id}",
                params={
                    "$select": (
                        "id,internetMessageId,conversationId,subject,from,"
                        "toRecipients,ccRecipients,bccRecipients,receivedDateTime,"
                        "hasAttachments,webLink,bodyPreview"
                    ),
                },
            )
        except Exception as _exc:  # noqa: BLE001
            log.exception(
                "Could not fetch message graph_id=%s account=%s",
                graph_message_id, account.id,
            )
            return None

    internet_id = msg.get("internetMessageId") or msg.get("id")
    if not internet_id:
        log.warning("Message %s has no internetMessageId; skipping", graph_message_id)
        return None

    existing = db.query(MSEmailReconciliation).filter(
        MSEmailReconciliation.ms_account_id == account.id,
        MSEmailReconciliation.internet_message_id == internet_id,
    ).first()
    if existing:
        return existing

    sender = (msg.get("from") or {}).get("emailAddress") or {}
    sender_email = (sender.get("address") or "").lower()
    sender_name = sender.get("name")

    recipient_emails = _flatten_recipients(msg)
    received_at = _parse_dt(msg.get("receivedDateTime"))
    subject = (msg.get("subject") or "").strip()
    body_preview = msg.get("bodyPreview")

    result = reconcile_email(
        db,
        organization_id=account.organization_id,
        sender_email=sender_email,
        recipient_emails=recipient_emails,
        subject=subject,
        body_preview=body_preview,
        conversation_id=msg.get("conversationId"),
    )

    row = MSEmailReconciliation(
        organization_id=account.organization_id,
        ms_account_id=account.id,
        graph_message_id=msg["id"],
        internet_message_id=internet_id,
        conversation_id=msg.get("conversationId"),
        subject=subject[:998],
        sender_email=sender_email,
        sender_name=sender_name,
        recipient_emails=recipient_emails,
        received_at=received_at,
        has_attachments=bool(msg.get("hasAttachments")),
        web_link=msg.get("webLink"),
        body_preview=body_preview,
        status=result.status.value,
        match_confidence=result.best_match.confidence if result.best_match else None,
        match_strategy=result.best_match.strategy if result.best_match else None,
        matched_link_type=result.best_match.link_type.value if result.best_match else None,
        matched_link_id=result.best_match.link_id if result.best_match else None,
        suggested_links=[c.to_suggested_link() for c in result.suggestions] or None,
        reconciled_at=datetime.now(timezone.utc)
        if result.status == ReconciliationStatus.AUTO_LINKED
        else None,
    )
    db.add(row)
    db.flush()
    log.info(
        "Ingested email graph_id=%s status=%s confidence=%s",
        msg["id"], result.status.value,
        f"{result.best_match.confidence:.2f}" if result.best_match else "n/a",
    )
    return row


def _flatten_recipients(msg: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("toRecipients", "ccRecipients", "bccRecipients"):
        for r in msg.get(key) or []:
            email = (r.get("emailAddress") or {}).get("address")
            if email:
                out.append(email.lower())
    seen: set[str] = set()
    deduped: list[str] = []
    for e in out:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
