"""Scheduled background jobs.

Wire these into your scheduler (APScheduler is already in the project).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .calendar_sync import pull_outlook_event_into_crm
from .email_ingest import ingest_message
from .graph_client import GraphClient
from .models import MSAccount, MSGraphSubscription
from .subscriptions import (
    delete_subscription,
    expiring_subscriptions,
    renew_subscription,
)

log = logging.getLogger(__name__)


async def renew_expiring_subscriptions(db: Session) -> int:
    expiring = expiring_subscriptions(db)
    renewed = 0
    for sub in expiring:
        try:
            await renew_subscription(db, sub)
            renewed += 1
        except Exception:
            log.exception(
                "Failed to renew subscription %s (kind=%s)", sub.id, sub.kind
            )
            sub.failure_count += 1
            db.flush()
    log.info("Renewed %s/%s expiring subscriptions", renewed, len(expiring))
    return renewed


async def delta_sync_account(db: Session, account: MSAccount) -> dict[str, int]:
    if not account.is_active:
        return {"emails": 0, "events": 0}

    counts = {"emails": 0, "events": 0}

    async with GraphClient(db, account) as gc:
        try:
            if account.email_delta_link:
                delta_response = await gc.get_absolute(account.email_delta_link)
            else:
                since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                delta_response = await gc.get(
                    "/me/mailFolders/inbox/messages/delta",
                    params={"$filter": f"receivedDateTime ge {since}"},
                )

            while True:
                for msg in delta_response.get("value", []):
                    if "@removed" in msg:
                        continue
                    msg_id = msg.get("id")
                    if msg_id:
                        try:
                            await ingest_message(db, account, msg_id)
                            counts["emails"] += 1
                        except Exception:
                            log.exception(
                                "Delta-sync email ingest failed (graph_id=%s)", msg_id
                            )

                next_link = delta_response.get("@odata.nextLink")
                if next_link:
                    delta_response = await gc.get_absolute(next_link)
                    continue
                account.email_delta_link = delta_response.get("@odata.deltaLink")
                break
        except Exception:
            log.exception("Email delta sync failed for account=%s", account.id)

        try:
            if account.calendar_delta_link:
                delta_response = await gc.get_absolute(account.calendar_delta_link)
            else:
                start = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
                end = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
                delta_response = await gc.get(
                    "/me/calendarView/delta",
                    params={"startDateTime": start, "endDateTime": end},
                )

            while True:
                for evt in delta_response.get("value", []):
                    if "@removed" in evt:
                        continue
                    evt_id = evt.get("id")
                    if evt_id:
                        try:
                            await pull_outlook_event_into_crm(db, account, evt_id)
                            counts["events"] += 1
                        except Exception:
                            log.exception(
                                "Delta-sync calendar pull failed (graph_id=%s)", evt_id
                            )

                next_link = delta_response.get("@odata.nextLink")
                if next_link:
                    delta_response = await gc.get_absolute(next_link)
                    continue
                account.calendar_delta_link = delta_response.get("@odata.deltaLink")
                break
        except Exception:
            log.exception("Calendar delta sync failed for account=%s", account.id)

    db.flush()
    return counts


async def delta_sync_all_active_accounts(db: Session) -> None:
    accounts = db.query(MSAccount).filter(MSAccount.is_active.is_(True)).all()
    sem = asyncio.Semaphore(4)

    async def _run(acc: MSAccount) -> None:
        async with sem:
            try:
                counts = await delta_sync_account(db, acc)
                log.info(
                    "Delta sync account=%s emails=%s events=%s",
                    acc.id, counts["emails"], counts["events"],
                )
            except Exception:
                log.exception("Delta sync failed for account=%s", acc.id)

    await asyncio.gather(*[_run(a) for a in accounts])


async def garbage_collect_subscriptions(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = db.query(MSGraphSubscription).filter(
        MSGraphSubscription.expiration_datetime < cutoff
    ).all()

    deleted = 0
    for sub in expired:
        try:
            await delete_subscription(db, sub)
            deleted += 1
        except Exception:
            log.exception("GC failed for subscription %s", sub.id)

    log.info("Garbage-collected %s expired subscriptions", deleted)
    return deleted
