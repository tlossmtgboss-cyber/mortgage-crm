"""FastAPI routes for OAuth, account status, calendar mirror, and reconciliation tab.

Mounts at: /api/v1/microsoft
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .auth import (
    build_authorization_url,
    exchange_code_for_token,
    generate_pkce_pair,
    upsert_account_from_token_response,
)
from .calendar_sync import (
    delete_crm_event_in_outlook,
    push_crm_event_to_outlook,
)
from .graph_client import GraphClient
from .models import (
    MSAccount,
    MSCalendarSyncMapping,
    MSEmailReconciliation,
    MSGraphSubscription,
    MSTeamsChatReconciliation,
    ReconciliationLinkType,
    ReconciliationStatus,
)
from .schemas import (
    CalendarSyncStatus,
    CRMEventUpsert,
    DismissRequest,
    EmailReconciliationItem,
    ManualLinkRequest,
    MSAccountStatus,
    ReconciliationListResponse,
    SubscriptionStatus,
    SuggestedLink,
    TeamsChatReconciliationItem,
)
from .subscriptions import ensure_all_subscriptions
from .webhooks import router as webhooks_router

from db import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["microsoft"])
router.include_router(webhooks_router)


@router.get("/ping")
async def ping():
    return {"pong": True}


def _get_current_user():
    from auth.dependencies import get_current_user
    return get_current_user


# ─────────────────────────────────────────────────────────────────────────
# OAuth flow
# ─────────────────────────────────────────────────────────────────────────

# In-memory state store for PKCE (use Redis in production if available)
_oauth_state_store: dict[str, tuple[str, int, int]] = {}


@router.post("/oauth/init")
async def oauth_init(
    request: Request,
    db: Session = Depends(get_db),
):
    import os
    import secrets as _secrets

    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    is_admin = bool(expected_key and api_key and _secrets.compare_digest(api_key, expected_key))

    if is_admin:
        from database.models.core import User
        user = db.query(User).order_by(User.id).first()
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No users found")
    else:
        _get_user = _get_current_user()
        user = await _get_user(request)

    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce_pair()

    _oauth_state_store[state] = (verifier, user.id, user.organization_id)

    url = build_authorization_url(state, challenge)
    return {"authorization_url": url, "state": state, "user_email": user.email}


@router.get("/oauth/callback")
async def oauth_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Session = Depends(get_db),
) -> Response:
    cached = _oauth_state_store.pop(state, None)
    if not cached:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "State expired or invalid")

    verifier, user_id, organization_id = cached

    token_response = await exchange_code_for_token(code, verifier)

    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        me_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token_response['access_token']}"},
        )
        me_resp.raise_for_status()
        me = me_resp.json()

    account = upsert_account_from_token_response(
        db,
        organization_id=organization_id,
        user_id=user_id,
        token_response=token_response,
        me=me,
    )
    await ensure_all_subscriptions(db, account)
    db.commit()

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/settings/integrations/microsoft365?connected=1", status_code=302)


@router.get("/account")
async def get_account_status(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    account = db.query(MSAccount).filter(
        MSAccount.organization_id == user.organization_id,
        MSAccount.user_id == user.id,
    ).first()
    if not account:
        return None

    subs = db.query(MSGraphSubscription).filter(
        MSGraphSubscription.ms_account_id == account.id
    ).all()

    return MSAccountStatus(
        id=account.id,
        upn=account.upn,
        display_name=account.display_name,
        is_active=account.is_active,
        scopes=account.scopes or [],
        last_error=account.last_error,
        connected_at=account.created_at,
        subscriptions=[
            SubscriptionStatus(
                kind=s.kind,
                expiration_datetime=s.expiration_datetime,
                last_renewed_at=s.last_renewed_at,
                failure_count=s.failure_count,
            )
            for s in subs
        ],
    )


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
) -> Response:
    account = db.query(MSAccount).filter(
        MSAccount.organization_id == user.organization_id,
        MSAccount.user_id == user.id,
    ).first()
    if account:
        subs = db.query(MSGraphSubscription).filter(
            MSGraphSubscription.ms_account_id == account.id
        ).all()
        for sub in subs:
            try:
                async with GraphClient(db, account) as gc:
                    await gc.delete(f"/subscriptions/{sub.graph_subscription_id}")
            except Exception:
                log.warning("Could not delete Graph subscription %s on disconnect", sub.id)
        db.delete(account)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────
# Calendar mirror
# ─────────────────────────────────────────────────────────────────────────


@router.get("/calendar/status")
async def calendar_status(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    account = _require_account(db, user)
    total = db.query(func.count(MSCalendarSyncMapping.id)).filter(
        MSCalendarSyncMapping.ms_account_id == account.id,
        MSCalendarSyncMapping.is_deleted.is_(False),
    ).scalar() or 0
    last_in = db.query(func.max(MSCalendarSyncMapping.last_synced_at)).filter(
        MSCalendarSyncMapping.ms_account_id == account.id,
        MSCalendarSyncMapping.direction == "outlook_to_crm",
    ).scalar()
    last_out = db.query(func.max(MSCalendarSyncMapping.last_synced_at)).filter(
        MSCalendarSyncMapping.ms_account_id == account.id,
        MSCalendarSyncMapping.direction == "crm_to_outlook",
    ).scalar()
    return CalendarSyncStatus(
        total_mapped_events=total,
        last_inbound_sync_at=last_in,
        last_outbound_sync_at=last_out,
        pending_outbound=0,
    )


@router.post("/calendar/push", status_code=status.HTTP_202_ACCEPTED)
async def push_event(
    payload: CRMEventUpsert,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    account = _require_account(db, user)
    mapping = await push_crm_event_to_outlook(db, account, payload)
    db.commit()
    return {"graph_event_id": mapping.graph_event_id}


@router.delete("/calendar/{crm_event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    crm_event_id: int,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    account = _require_account(db, user)
    await delete_crm_event_in_outlook(db, account, crm_event_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────
# Reconciliation tab
# ─────────────────────────────────────────────────────────────────────────


@router.get("/reconciliation")
async def list_reconciliation(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(le=100)] = 50,
):
    account = _require_account(db, user)
    statuses = status_filter or [
        ReconciliationStatus.UNMATCHED.value,
        ReconciliationStatus.SUGGESTED.value,
    ]

    emails = db.query(MSEmailReconciliation).filter(
        MSEmailReconciliation.ms_account_id == account.id,
        MSEmailReconciliation.status.in_(statuses),
    ).order_by(MSEmailReconciliation.received_at.desc()).limit(limit).all()

    teams_msgs = db.query(MSTeamsChatReconciliation).filter(
        MSTeamsChatReconciliation.ms_account_id == account.id,
        MSTeamsChatReconciliation.status.in_(statuses),
    ).order_by(MSTeamsChatReconciliation.sent_at.desc()).limit(limit).all()

    total_unmatched = db.query(func.count()).select_from(MSEmailReconciliation).filter(
        MSEmailReconciliation.ms_account_id == account.id,
        MSEmailReconciliation.status == ReconciliationStatus.UNMATCHED.value,
    ).scalar() or 0

    total_suggested = db.query(func.count()).select_from(MSEmailReconciliation).filter(
        MSEmailReconciliation.ms_account_id == account.id,
        MSEmailReconciliation.status == ReconciliationStatus.SUGGESTED.value,
    ).scalar() or 0

    return ReconciliationListResponse(
        emails=[_email_to_item(e) for e in emails],
        teams_chats=[_teams_to_item(t) for t in teams_msgs],
        total_unmatched=total_unmatched,
        total_suggested=total_suggested,
    )


@router.post("/reconciliation/email/{email_id}/link")
async def link_email(
    email_id: int,
    payload: ManualLinkRequest,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    row = db.query(MSEmailReconciliation).filter(
        MSEmailReconciliation.id == email_id,
        MSEmailReconciliation.organization_id == user.organization_id,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")

    row.matched_link_type = payload.link_type
    row.matched_link_id = payload.link_id
    row.status = ReconciliationStatus.MANUALLY_LINKED.value
    row.match_confidence = 1.0
    row.match_strategy = "manual"
    row.reconciled_at = datetime.now(timezone.utc)
    row.reconciled_by_user_id = user.id
    db.commit()
    return {"ok": True}


@router.post("/reconciliation/email/{email_id}/dismiss")
async def dismiss_email(
    email_id: int,
    payload: DismissRequest,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    row = db.query(MSEmailReconciliation).filter(
        MSEmailReconciliation.id == email_id,
        MSEmailReconciliation.organization_id == user.organization_id,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")

    row.status = ReconciliationStatus.DISMISSED.value
    row.reconciled_at = datetime.now(timezone.utc)
    row.reconciled_by_user_id = user.id
    db.commit()
    return {"ok": True}


@router.post("/reconciliation/teams/{message_id}/link")
async def link_teams(
    message_id: int,
    payload: ManualLinkRequest,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    row = db.query(MSTeamsChatReconciliation).filter(
        MSTeamsChatReconciliation.id == message_id,
        MSTeamsChatReconciliation.organization_id == user.organization_id,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    row.matched_link_type = payload.link_type
    row.matched_link_id = payload.link_id
    row.status = ReconciliationStatus.MANUALLY_LINKED.value
    row.match_confidence = 1.0
    row.match_strategy = "manual"
    row.reconciled_at = datetime.now(timezone.utc)
    row.reconciled_by_user_id = user.id
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────
# Bootstrap from existing Microsoft OAuth tokens (one-shot, admin only)
# ─────────────────────────────────────────────────────────────────────────


@router.post("/bootstrap")
async def bootstrap_from_credentials(
    request: Request,
    db: Session = Depends(get_db),
):
    """Bootstrap MS365 integration using ROPC (username/password) grant.
    Admin API key required. Body: {"username": "...", "password": "..."}"""
    import os
    import secrets as _secrets
    import httpx
    from .auth import upsert_account_from_token_response
    from .subscriptions import ensure_all_subscriptions
    from .tasks import delta_sync_account
    from .config import get_settings, GRAPH_SCOPES

    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not (expected_key and api_key and _secrets.compare_digest(api_key, expected_key)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin API key required")

    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username and password required")

    s = get_settings()

    # ROPC token exchange — no browser needed
    token_url = f"https://login.microsoftonline.com/{s.tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": s.client_id,
        "client_secret": s.client_secret.get_secret_value(),
        "scope": " ".join(GRAPH_SCOPES),
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    from fastapi.responses import JSONResponse
    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(token_url, data=data)
        if token_resp.status_code != 200:
            err = token_resp.json()
            return JSONResponse(
                status_code=400,
                content={
                    "error": err.get("error", "unknown"),
                    "detail": err.get("error_description", "Token exchange failed"),
                    "codes": err.get("error_codes", []),
                },
            )
        token_response = token_resp.json()

    # Get user profile from Graph
    async with httpx.AsyncClient(timeout=30.0) as client:
        me_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token_response['access_token']}"},
        )
        me_resp.raise_for_status()
        me = me_resp.json()

    # Resolve CRM user
    from database.models.core import User
    user = db.query(User).order_by(User.id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No CRM user found")

    account = upsert_account_from_token_response(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        token_response=token_response,
        me=me,
    )

    sub_results = []
    try:
        await ensure_all_subscriptions(db, account)
        sub_results.append("subscriptions created")
    except Exception as exc:
        sub_results.append(f"subscriptions failed: {exc}")

    db.commit()

    sync_counts = {"emails": 0, "events": 0}
    try:
        sync_counts = await delta_sync_account(db, account)
        db.commit()
    except Exception as exc:
        sub_results.append(f"initial sync failed: {exc}")
        db.rollback()

    return {
        "status": "connected",
        "account_id": account.id,
        "upn": account.upn,
        "display_name": account.display_name,
        "subscriptions": sub_results,
        "initial_sync": sync_counts,
    }


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _require_account(db: Session, user) -> MSAccount:
    account = db.query(MSAccount).filter(
        MSAccount.organization_id == user.organization_id,
        MSAccount.user_id == user.id,
        MSAccount.is_active.is_(True),
    ).first()
    if not account:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Microsoft 365 account not connected. Connect via Settings > Integrations.",
        )
    return account


def _email_to_item(row: MSEmailReconciliation) -> EmailReconciliationItem:
    suggested = None
    if row.suggested_links:
        suggested = [
            SuggestedLink(
                link_type=s["link_type"],
                link_id=s["link_id"],
                label=s["label"],
                confidence=s["confidence"],
                strategy=s["strategy"],
                metadata=s.get("metadata", {}),
            )
            for s in row.suggested_links
        ]
    return EmailReconciliationItem(
        id=row.id,
        subject=row.subject,
        sender_email=row.sender_email,
        sender_name=row.sender_name,
        recipient_emails=row.recipient_emails or [],
        received_at=row.received_at,
        has_attachments=row.has_attachments,
        body_preview=row.body_preview,
        web_link=row.web_link,
        status=row.status,
        match_confidence=row.match_confidence,
        match_strategy=row.match_strategy,
        matched_link_type=row.matched_link_type,
        matched_link_id=row.matched_link_id,
        suggested_links=suggested,
    )


def _teams_to_item(row: MSTeamsChatReconciliation) -> TeamsChatReconciliationItem:
    suggested = None
    if row.suggested_links:
        suggested = [
            SuggestedLink(
                link_type=s["link_type"],
                link_id=s["link_id"],
                label=s["label"],
                confidence=s["confidence"],
                strategy=s["strategy"],
                metadata=s.get("metadata", {}),
            )
            for s in row.suggested_links
        ]
    return TeamsChatReconciliationItem(
        id=row.id,
        chat_topic=row.chat_topic,
        sender_email=row.sender_email,
        sender_name=row.sender_name,
        sent_at=row.sent_at,
        body_text=row.body_text,
        web_link=row.web_link,
        status=row.status,
        match_confidence=row.match_confidence,
        match_strategy=row.match_strategy,
        matched_link_type=row.matched_link_type,
        matched_link_id=row.matched_link_id,
        suggested_links=suggested,
    )
