"""Manage Microsoft Graph webhook subscriptions.

Graph subscriptions expire (max ~70.5 hours). We create them on connect,
renew them on a schedule, and recreate them if Graph returns 404.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import (
    SUBSCRIPTION_CHANGE_TYPES,
    SUBSCRIPTION_RESOURCES,
    get_settings,
)
from .graph_client import GraphAPIError, GraphClient
from .models import MSAccount, MSGraphSubscription, SubscriptionKind

log = logging.getLogger(__name__)


def _client_state_for(account_id: int, kind: str) -> str:
    s = get_settings()
    raw = f"{account_id}:{kind}:{s.webhook_client_state.get_secret_value()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_client_state(received: str, account_id: int, kind: str) -> bool:
    expected = _client_state_for(account_id, kind)
    if len(received) != len(expected):
        return False
    diff = 0
    for a, b in zip(received, expected):
        diff |= ord(a) ^ ord(b)
    return diff == 0


def _max_minutes_for(kind: str) -> int:
    s = get_settings()
    return {
        SubscriptionKind.CALENDAR.value: s.sub_max_minutes_calendar,
        SubscriptionKind.EMAIL.value: s.sub_max_minutes_messages,
        SubscriptionKind.TEAMS_CHATS.value: s.sub_max_minutes_chats,
    }[kind]


async def create_subscription(
    db: Session, account: MSAccount, kind: str
) -> MSGraphSubscription:
    s = get_settings()
    resource = SUBSCRIPTION_RESOURCES[kind]
    change_type = SUBSCRIPTION_CHANGE_TYPES[kind]
    expiration = datetime.now(timezone.utc) + timedelta(minutes=_max_minutes_for(kind))
    notification_url = f"{s.webhook_base_url}/{kind}"
    client_state = _client_state_for(account.id, kind)

    payload = {
        "changeType": change_type,
        "notificationUrl": notification_url,
        "resource": resource,
        "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
        "clientState": client_state,
        "latestSupportedTlsVersion": "v1_2",
    }

    async with GraphClient(db, account) as gc:
        result = await gc.post("/subscriptions", json=payload)

    sub = MSGraphSubscription(
        organization_id=account.organization_id,
        ms_account_id=account.id,
        kind=kind,
        graph_subscription_id=result["id"],
        resource=resource,
        change_type=change_type,
        notification_url=notification_url,
        client_state_hash=hashlib.sha256(client_state.encode()).hexdigest(),
        expiration_datetime=_parse_graph_dt(result["expirationDateTime"]),
        last_renewed_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    db.flush()
    log.info(
        "Created %s subscription for account=%s graph_id=%s",
        kind, account.id, result["id"],
    )
    return sub


async def renew_subscription(
    db: Session, sub: MSGraphSubscription
) -> MSGraphSubscription:
    new_expiration = datetime.now(timezone.utc) + timedelta(
        minutes=_max_minutes_for(sub.kind)
    )
    payload = {"expirationDateTime": new_expiration.isoformat().replace("+00:00", "Z")}

    account = db.query(MSAccount).get(sub.ms_account_id)
    if not account:
        raise RuntimeError(f"Subscription {sub.id} has no account")

    async with GraphClient(db, account) as gc:
        try:
            result = await gc.patch(f"/subscriptions/{sub.graph_subscription_id}", json=payload)
        except GraphAPIError as exc:
            if exc.status == 404:
                log.warning("Subscription %s not found at Graph — recreating", sub.id)
                db.delete(sub)
                db.flush()
                return await create_subscription(db, account, sub.kind)
            sub.failure_count += 1
            db.flush()
            raise

    sub.expiration_datetime = _parse_graph_dt(result["expirationDateTime"])
    sub.last_renewed_at = datetime.now(timezone.utc)
    sub.failure_count = 0
    db.flush()
    return sub


async def delete_subscription(db: Session, sub: MSGraphSubscription) -> None:
    account = db.query(MSAccount).get(sub.ms_account_id)
    if account:
        async with GraphClient(db, account) as gc:
            try:
                await gc.delete(f"/subscriptions/{sub.graph_subscription_id}")
            except GraphAPIError as exc:
                if exc.status != 404:
                    log.warning("Failed to delete Graph subscription: %s", exc)
    db.delete(sub)
    db.flush()


def expiring_subscriptions(db: Session) -> list[MSGraphSubscription]:
    s = get_settings()
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=s.webhook_renew_buffer_minutes)
    return db.query(MSGraphSubscription).filter(
        MSGraphSubscription.expiration_datetime <= cutoff
    ).all()


async def ensure_all_subscriptions(db: Session, account: MSAccount) -> None:
    existing_kinds = {
        s.kind for s in db.query(MSGraphSubscription).filter(
            MSGraphSubscription.ms_account_id == account.id
        ).all()
    }
    for kind in SubscriptionKind:
        if kind.value not in existing_kinds:
            try:
                await create_subscription(db, account, kind.value)
            except GraphAPIError as exc:
                log.warning(
                    "Could not create %s subscription for account=%s: %s",
                    kind.value, account.id, exc,
                )


def _parse_graph_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
