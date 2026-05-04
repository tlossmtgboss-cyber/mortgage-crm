"""
Automated Email Sync Scheduler

Fetches loan-related emails from Microsoft Graph (client credentials flow)
every 5 minutes and ingests them into the Data Reconciliation Engine.

No per-user OAuth required — uses app-level permissions with admin consent.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

LOAN_RELATED_SENDERS = {
    "leads@email.realtor.com",
    "no-reply@mortgage.zillow.com",
    "donotreply@optimalblue.com",
    "alerts@trustengine.com",
    "welcome@topofmind.com",
    "noreply@topofmind.com",
    "notifications@simplenexus.com",
    "listingupdates@flexmail.flexmls.com",
    "notifications@domo.com",
}

LOAN_KEYWORDS = [
    "closing", "rate lock", "change request", "new lead", "new contact",
    "pre-approval", "appraisal", "title", "underwriting", "mortgage coach",
    "loan comparison", "power of attorney", "wire information",
    "conditional approval", "clear to close", "funded",
]


def _is_loan_related(subject: str, sender: str, body: str) -> bool:
    sender_lower = (sender or "").lower().strip()
    if sender_lower in LOAN_RELATED_SENDERS:
        return True

    text = f"{subject} {body}".lower()
    return any(kw in text for kw in LOAN_KEYWORDS)


async def _get_app_token() -> Optional[str]:
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID", "").strip()
    client_id = os.environ.get("MICROSOFT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "").strip()

    if not all([tenant_id, client_id, client_secret]):
        logger.warning("Microsoft credentials not configured — email sync disabled")
        return None

    url = GRAPH_TOKEN_URL.format(tenant_id=tenant_id)
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        })

    if resp.status_code != 200:
        logger.error(f"Failed to get Graph token: {resp.status_code} {resp.text[:200]}")
        return None

    return resp.json().get("access_token")


async def _fetch_recent_emails(token: str, user_email: str, since_minutes: int = 6):
    since = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{GRAPH_BASE}/users/{user_email}/messages"
    params = {
        "$filter": f"receivedDateTime ge {since}",
        "$select": "id,subject,sender,toRecipients,ccRecipients,bodyPreview,body,receivedDateTime,hasAttachments,internetMessageId",
        "$top": "50",
        "$orderby": "receivedDateTime desc",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    if resp.status_code == 403:
        logger.error("Graph API 403 — app may lack Mail.Read application permission")
        return []
    if resp.status_code != 200:
        logger.error(f"Graph API error fetching emails: {resp.status_code} {resp.text[:200]}")
        return []

    return resp.json().get("value", [])


async def run_email_sync():
    """Main sync function — called by scheduler every 5 minutes."""
    from db import SessionLocal
    from database.models import IncomingDataEvent, BlockedSender, User

    user_email = os.environ.get("EMAIL_SYNC_USER", "tloss@cmghomeloans.com")

    token = await _get_app_token()
    if not token:
        return

    emails = await _fetch_recent_emails(token, user_email)
    if not emails:
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            logger.error(f"Email sync user not found: {user_email}")
            return

        blocked = {
            r.sender_email.lower()
            for r in db.query(BlockedSender).filter(BlockedSender.user_id == user.id).all()
        }

        existing_ids = set()
        ext_ids = [e.get("internetMessageId") for e in emails if e.get("internetMessageId")]
        if ext_ids:
            from sqlalchemy import text
            rows = db.execute(
                text("SELECT external_message_id FROM incoming_data_events WHERE user_id = :uid AND external_message_id = ANY(:ids)"),
                {"uid": user.id, "ids": ext_ids},
            ).fetchall()
            existing_ids = {r[0] for r in rows}

        ingested = 0
        for email in emails:
            msg_id = email.get("internetMessageId", "")
            if msg_id in existing_ids:
                continue

            sender_addr = email.get("sender", {}).get("emailAddress", {}).get("address", "")
            if sender_addr.lower() in blocked:
                continue

            subject = email.get("subject", "")
            body_content = email.get("body", {}).get("content", "")
            body_preview = email.get("bodyPreview", "")

            if not _is_loan_related(subject, sender_addr, body_preview):
                continue

            recipients = [
                r.get("emailAddress", {}).get("address", "")
                for r in email.get("toRecipients", []) + email.get("ccRecipients", [])
            ]

            content_type = email.get("body", {}).get("contentType", "text")
            raw_text = body_content if content_type == "text" else None
            raw_html = body_content if content_type == "html" else None

            event = IncomingDataEvent(
                source="outlook_auto_sync",
                raw_text=raw_text,
                raw_html=raw_html,
                subject=subject,
                sender=sender_addr,
                recipients=recipients if recipients else None,
                external_message_id=msg_id,
                user_id=user.id,
                processed=False,
            )
            db.add(event)
            ingested += 1

        if ingested > 0:
            db.commit()
            logger.info(f"Email sync: ingested {ingested} loan-related emails for {user_email}")

            # Trigger extraction on new events
            await _extract_new_events(db, user)
        else:
            logger.debug("Email sync: no new loan-related emails")

    except Exception as e:
        logger.error(f"Email sync error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


async def _extract_new_events(db, user):
    """Run extraction on unprocessed events."""
    from database.models import IncomingDataEvent, ExtractedData

    try:
        from services.dre_helpers import classify_email_content, extract_loan_fields, match_entity
    except ImportError:
        try:
            import main
            classify_email_content = main.classify_email_content
            extract_loan_fields = main.extract_loan_fields
            match_entity = main.match_entity
        except Exception as e:
            logger.warning(f"Could not import extraction helpers: {e}")
            return

    unprocessed = db.query(IncomingDataEvent).filter(
        IncomingDataEvent.user_id == user.id,
        IncomingDataEvent.processed == False
    ).limit(20).all()

    for event in unprocessed:
        try:
            content = event.raw_text or event.raw_html or ""
            subject = event.subject or ""

            if not content and not subject:
                event.processed = True
                continue

            classification = classify_email_content(content, subject)
            if classification["category"] == "unrelated" or classification.get("confidence", 0) < 0.5:
                event.processed = True
                continue

            fields = extract_loan_fields(content, classification["category"]) if classification["category"] != "unrelated" else {}
            if not fields:
                fields = {"email_summary": {"value": subject, "confidence": 0.7}}

            entity_match = match_entity(fields, db, user.id)

            confidences = [f.get("confidence", 0.0) for f in fields.values()]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

            status = "pending_review"
            if avg_confidence < 0.60 or entity_match["confidence"] < 0.50:
                status = "needs_review"

            extracted = ExtractedData(
                event_id=event.id,
                category=classification["category"],
                subcategory=classification.get("subcategory"),
                fields=fields,
                match_entity_type=entity_match["entity_type"],
                match_entity_id=entity_match["entity_id"],
                match_confidence=entity_match["confidence"],
                ai_confidence=avg_confidence,
                status=status,
            )
            db.add(extracted)
            event.processed = True
        except Exception as e:
            logger.error(f"Extraction failed for event {event.id}: {e}")

    db.commit()
