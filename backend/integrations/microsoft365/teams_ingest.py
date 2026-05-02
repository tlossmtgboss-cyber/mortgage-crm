"""Inbound Teams 1:1 chat ingestion.

Fetches the message and chat metadata, filters to one-on-one conversations,
and reconciles against CRM records.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .graph_client import GraphAPIError, GraphClient
from .models import MSAccount, MSTeamsChatReconciliation, ReconciliationStatus
from .reconciliation import reconcile_teams_message

log = logging.getLogger(__name__)


async def ingest_chat_message(
    db: Session,
    account: MSAccount,
    *,
    chat_id: str,
    message_id: str,
) -> MSTeamsChatReconciliation | None:
    async with GraphClient(db, account) as gc:
        try:
            msg = await gc.get(f"/chats/{chat_id}/messages/{message_id}")
            chat = await gc.get(f"/chats/{chat_id}")
        except GraphAPIError:
            log.exception(
                "Could not fetch chat message %s/%s account=%s",
                chat_id, message_id, account.id,
            )
            return None

    if chat.get("chatType") != "oneOnOne":
        return None

    sender = (msg.get("from") or {}).get("user") or {}
    if not sender:
        return None

    sender_id = sender.get("id")
    if sender_id and sender_id == account.ms_user_id:
        return None

    existing = db.query(MSTeamsChatReconciliation).filter(
        MSTeamsChatReconciliation.ms_account_id == account.id,
        MSTeamsChatReconciliation.graph_chat_id == chat_id,
        MSTeamsChatReconciliation.graph_message_id == message_id,
    ).first()
    if existing:
        return existing

    sender_email = await _resolve_user_email(db, account, sender_id) if sender_id else ""

    body = msg.get("body") or {}
    body_text = _strip_html(body.get("content") or "")
    sent_at = _parse_dt(msg.get("createdDateTime"))

    result = reconcile_teams_message(
        db,
        organization_id=account.organization_id,
        sender_email=sender_email,
        body_text=body_text,
    )

    row = MSTeamsChatReconciliation(
        organization_id=account.organization_id,
        ms_account_id=account.id,
        graph_chat_id=chat_id,
        graph_message_id=message_id,
        chat_topic=chat.get("topic"),
        is_one_on_one=True,
        sender_email=sender_email,
        sender_name=sender.get("displayName"),
        sent_at=sent_at,
        body_text=body_text[:8000] if body_text else None,
        web_link=msg.get("webUrl"),
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
    return row


async def _resolve_user_email(
    db: Session, account: MSAccount, aad_user_id: str
) -> str:
    async with GraphClient(db, account) as gc:
        try:
            user = await gc.get(f"/users/{aad_user_id}", params={"$select": "mail,userPrincipalName"})
        except GraphAPIError:
            return ""
    return (user.get("mail") or user.get("userPrincipalName") or "").lower()


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
