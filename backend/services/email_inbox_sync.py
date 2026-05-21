"""Lightweight Outlook inbox/sent sync + email-address lead matcher.

Runs on a 5-minute schedule.  For each user with a valid Microsoft OAuth
token it fetches recent emails from Inbox and Sent Items via Graph API,
stores them in the ``emails`` table, and links them to leads by matching
sender/recipient addresses against ``leads.email``.

No AI processing — just fast, deterministic email-to-lead linking so
every borrower conversation shows up in the client-file timeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger("email_inbox_sync")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SELECT = (
    "id,subject,bodyPreview,body,from,toRecipients,"
    "receivedDateTime,hasAttachments,isRead"
)
GRAPH_TIMEOUT = 30
SYNC_LOOKBACK_HOURS = 6
FETCH_LIMIT = 50


async def _fetch_folder(
    client: httpx.AsyncClient,
    access_token: str,
    folder: str,
    since: Optional[datetime] = None,
    limit: int = FETCH_LIMIT,
) -> list[dict]:
    params: dict[str, str] = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$select": GRAPH_SELECT,
    }
    if since:
        params["$filter"] = (
            f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

    try:
        resp = await client.get(
            f"{GRAPH_BASE}/me/mailFolders/{folder}/messages",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            logger.warning(
                "Graph API returned %d for folder %s",
                resp.status_code,
                folder,
            )
            return []
        return resp.json().get("value", [])
    except Exception as e:
        logger.error("Graph fetch error (%s): %s", folder, e)
        return []


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        raw = raw.rstrip("Z")
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _store_emails(
    db: Session,
    emails: list[dict],
    user_id: int,
    org_id: int,
    folder: str,
) -> int:
    from database.models.communication import Email

    msg_ids = [m.get("id") for m in emails if m.get("id")]
    if not msg_ids:
        return 0

    existing_ids = set(
        db.execute(
            select(Email.message_id).where(
                Email.message_id.in_(msg_ids),
                Email.organization_id == org_id,
            )
        ).scalars().all()
    )

    stored = 0
    for msg in emails:
        msg_id = msg.get("id")
        if not msg_id or msg_id in existing_ids:
            continue

        sender = msg.get("from", {}).get("emailAddress", {})
        recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in msg.get("toRecipients", [])
        ]
        body_obj = msg.get("body", {})
        body_text = msg.get("bodyPreview", "")
        if body_obj.get("contentType") == "text" and body_obj.get("content"):
            body_text = body_obj["content"]

        email = Email(
            organization_id=org_id,
            user_id=user_id,
            message_id=msg_id,
            sender_email=sender.get("address", ""),
            sender_name=sender.get("name", ""),
            recipient_emails=recipients,
            subject=msg.get("subject", ""),
            body_text=body_text,
            body_html=(
                body_obj.get("content", "")
                if body_obj.get("contentType") == "html"
                else ""
            ),
            received_date=_parse_dt(msg.get("receivedDateTime")),
            is_read=msg.get("isRead", False),
            has_attachments=msg.get("hasAttachments", False),
            folder_name=folder,
            processed=False,
        )
        try:
            db.add(email)
            db.flush()
            stored += 1
        except IntegrityError:
            db.rollback()

    return stored


def match_unlinked_emails(db: Session, org_id: int) -> int:
    """Link emails with no lead_id to leads by address match. Returns count."""
    from database.models.communication import Email
    from database.models.lead_loan import Lead

    unlinked = (
        db.execute(
            select(Email)
            .where(
                Email.organization_id == org_id,
                Email.lead_id.is_(None),
            )
            .order_by(Email.received_date.desc())
            .limit(500)
        )
        .scalars()
        .all()
    )
    if not unlinked:
        return 0

    all_addrs: set[str] = set()
    for e in unlinked:
        if e.sender_email:
            all_addrs.add(e.sender_email.lower())
        for r in e.recipient_emails or []:
            if r:
                all_addrs.add(r.lower())

    if not all_addrs:
        return 0

    leads = db.execute(
        select(Lead.id, Lead.email).where(
            Lead.organization_id == org_id,
            Lead.email.isnot(None),
            func.lower(Lead.email).in_(all_addrs),
        )
    ).all()

    email_to_lead: dict[str, int] = {}
    for lead_id, lead_email in leads:
        if lead_email:
            email_to_lead[lead_email.lower()] = lead_id

    if not email_to_lead:
        return 0

    matched = 0
    for e in unlinked:
        if e.sender_email and e.sender_email.lower() in email_to_lead:
            e.lead_id = email_to_lead[e.sender_email.lower()]
            matched += 1
            continue
        for r in e.recipient_emails or []:
            if r and r.lower() in email_to_lead:
                e.lead_id = email_to_lead[r.lower()]
                matched += 1
                break

    return matched


async def sync_user_emails(
    oauth_record,
    db: Session,
    user_id: int,
    org_id: int,
) -> dict:
    from services.dre_helpers import validate_microsoft_token

    token_result = await validate_microsoft_token(oauth_record, db)
    if not token_result.get("valid"):
        return {"error": token_result.get("error"), "stored": 0, "matched": 0}

    access_token = token_result["access_token"]

    since = oauth_record.last_sync_at
    if not since:
        since = datetime.now(timezone.utc) - timedelta(hours=SYNC_LOOKBACK_HOURS)
    elif since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as http:
        inbox = await _fetch_folder(http, access_token, "Inbox", since)
        sent = await _fetch_folder(http, access_token, "SentItems", since)

    stored = 0
    stored += _store_emails(db, inbox, user_id, org_id, "Inbox")
    stored += _store_emails(db, sent, user_id, org_id, "SentItems")
    db.commit()

    matched = match_unlinked_emails(db, org_id)
    oauth_record.last_sync_at = datetime.now(timezone.utc)
    db.commit()

    if stored or matched:
        logger.info(
            "Email sync user=%d: stored=%d matched=%d",
            user_id,
            stored,
            matched,
        )

    return {"stored": stored, "matched": matched}


async def sync_all_users() -> dict:
    """Sync emails for every user with an active Microsoft OAuth token.

    Creates a fresh RLS-scoped DB session per user to enforce tenant
    isolation and avoid holding a single connection for the entire cycle.
    The discovery query uses a bare session since MicrosoftOAuthToken has
    no organization_id column — only id and user_id are selected (no tokens).
    """
    from db import SessionLocal, get_db_with_tenant
    from database.models.microsoft import MicrosoftOAuthToken
    from database.models.core import User

    discovery_db = SessionLocal()
    try:
        rows = discovery_db.execute(
            select(
                MicrosoftOAuthToken.id,
                MicrosoftOAuthToken.user_id,
            ).where(
                MicrosoftOAuthToken.sync_enabled.is_(True),
                MicrosoftOAuthToken.access_token.isnot(None),
            )
        ).all()
    finally:
        discovery_db.close()

    if not rows:
        return {"users": 0, "stored": 0, "matched": 0}

    # Resolve org_id per user with a lightweight lookup session
    user_orgs: list[tuple[int, int, int]] = []  # (token_id, user_id, org_id)
    lookup_db = SessionLocal()
    try:
        for token_id, user_id in rows:
            org_id = lookup_db.execute(
                select(User.organization_id).where(User.id == user_id)
            ).scalar()
            if org_id:
                user_orgs.append((token_id, user_id, org_id))
    finally:
        lookup_db.close()

    total_stored = 0
    total_matched = 0
    synced_users = 0

    for token_id, user_id, org_id in user_orgs:
        try:
            with get_db_with_tenant(org_id) as db:
                tok = db.execute(
                    select(MicrosoftOAuthToken).where(
                        MicrosoftOAuthToken.id == token_id
                    )
                ).scalar()
                if not tok:
                    continue

                result = await sync_user_emails(tok, db, user_id, org_id)
                total_stored += result.get("stored", 0)
                total_matched += result.get("matched", 0)
                synced_users += 1
        except Exception as e:
            logger.error("Email sync failed for user %d: %s", user_id, e)

    return {"users": synced_users, "stored": total_stored, "matched": total_matched}
