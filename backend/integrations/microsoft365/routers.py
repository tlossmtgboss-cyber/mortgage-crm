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


@router.get("/calendar/outbound-status")
async def outbound_sync_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Check if outbound calendar sync to Outlook is ready (DRE tokens valid)."""
    import os
    import secrets as _secrets

    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not (expected_key and api_key and _secrets.compare_digest(api_key, expected_key)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin API key required")

    from fastapi.responses import JSONResponse
    from database.models.core import User
    from database.models.microsoft import MicrosoftOAuthToken

    user = db.query(User).order_by(User.id).first()
    if not user:
        return JSONResponse(content={"ready": False, "error": "No CRM user found"})

    all_tokens = db.query(MicrosoftOAuthToken).all()
    oauth = None
    for t in all_tokens:
        if t.user_id == user.id:
            oauth = t
            break
    if not oauth and all_tokens:
        oauth = all_tokens[0]

    if not oauth:
        return JSONResponse(content={
            "ready": False,
            "user_id": user.id,
            "user_email": user.email,
            "all_token_count": len(all_tokens),
            "error": "No MicrosoftOAuthToken records exist",
        })

    from services.dre_helpers import validate_microsoft_token
    validation = await validate_microsoft_token(oauth, db)

    return JSONResponse(content={
        "ready": validation.get("valid", False),
        "user_id": user.id,
        "user_email": user.email,
        "token_email": oauth.email_address,
        "token_expires_at": str(oauth.token_expires_at) if oauth.token_expires_at else None,
        "validation_error": validation.get("error") if not validation.get("valid") else None,
        "needs_reauth": validation.get("needs_reauth", False),
    })


@router.post("/calendar/test-sync")
async def test_outlook_sync(
    request: Request,
    db: Session = Depends(get_db),
):
    """Send a test .ics invite to verify Outlook calendar sync works."""
    import os
    import secrets as _secrets
    from datetime import datetime as _dt, timedelta, timezone as _tz
    from fastapi.responses import JSONResponse

    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not (expected_key and api_key and _secrets.compare_digest(api_key, expected_key)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin API key required")

    outlook_email = os.environ.get("OUTLOOK_SYNC_EMAIL", "")
    if not outlook_email:
        return JSONResponse(content={"success": False, "error": "OUTLOOK_SYNC_EMAIL not set"})

    from services.outlook_calendar_sync import push_appointment_to_outlook

    class _FakeAppointment:
        id = 99999
        title = "Test Sync from Perennia"
        scheduled_start = _dt.now(_tz.utc) + timedelta(days=1)
        scheduled_end = _dt.now(_tz.utc) + timedelta(days=1, minutes=30)
        description = "This is a test event to verify Outlook calendar sync."
        location = ""
        video_link = ""
        attendee_name = "Test"
        attendee_email = ""
        assigned_user_id = None
        created_by_user_id = None

    result = await push_appointment_to_outlook(db, _FakeAppointment(), outlook_email)
    return JSONResponse(content=result)


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
# Bulk calendar import (via MCP / admin CLI)
# ─────────────────────────────────────────────────────────────────────────

@router.post("/calendar/import")
async def bulk_import_calendar(
    request: Request,
    db: Session = Depends(get_db),
):
    """Import Outlook calendar events into CRM appointments.
    Admin API key required. Body: {"events": [...]}"""
    import os
    import secrets as _secrets
    from datetime import datetime as _dt, timezone as _tz
    from fastapi.responses import JSONResponse

    api_key = request.headers.get("X-API-Key", "")
    expected_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not (expected_key and api_key and _secrets.compare_digest(api_key, expected_key)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin API key required")

    body = await request.json()
    events = body.get("events", [])
    if not events:
        return JSONResponse(content={"imported": 0, "skipped": 0})

    from database.models.core import User
    user = db.query(User).order_by(User.id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No CRM user found")

    from database.models.scheduler import Appointment

    imported = 0
    skipped = 0
    errors = []

    for evt in events:
        outlook_id = evt.get("outlook_id", "")
        subject = evt.get("subject", "No subject")

        if outlook_id:
            existing = db.query(Appointment).filter(
                Appointment.outlook_event_id == outlook_id,
            ).first()
            if existing:
                skipped += 1
                continue

        try:
            start_str = evt.get("start", "")
            end_str = evt.get("end", "")
            start = _dt.fromisoformat(start_str.replace("Z", "+00:00"))
            end = _dt.fromisoformat(end_str.replace("Z", "+00:00"))
            duration = int((end - start).total_seconds() / 60)

            location = evt.get("location", "") or ""
            is_teams = "teams" in location.lower()
            is_zoom = "zoom" in location.lower()
            is_meet = "meet.google" in location.lower()
            is_video = is_teams or is_zoom or is_meet
            is_phone = location.startswith("+") or location.startswith("(")

            video_link = ""
            if is_teams or is_zoom or is_meet:
                video_link = location

            meeting_mode = "video" if is_video else ("phone" if is_phone else "in_person")

            attendee_list = evt.get("attendees", [])
            attendee_name = ""
            attendee_email = ""
            if isinstance(attendee_list, list) and attendee_list:
                first = attendee_list[0] if isinstance(attendee_list[0], str) else ""
                if "@" in first:
                    attendee_email = first
                else:
                    attendee_name = first

            appt = Appointment(
                organization_id=user.organization_id,
                assigned_user_id=user.id,
                created_by_user_id=user.id,
                title=subject[:255],
                description=f"Imported from Outlook",
                scheduled_start=start,
                scheduled_end=end,
                duration_minutes=max(duration, 1),
                timezone="America/New_York",
                location=location[:255] if not is_video else "Video Call",
                video_link=video_link[:500] if video_link else None,
                meeting_mode=meeting_mode,
                attendee_name=attendee_name[:255] if attendee_name else None,
                attendee_email=attendee_email[:255] if attendee_email else None,
                external_id=outlook_id[:100] if outlook_id else None,
                external_source="outlook",
                outlook_event_id=outlook_id[:255] if outlook_id else None,
                status="booked",
                booked_by_ai=False,
            )
            db.add(appt)
            imported += 1
        except Exception as exc:
            errors.append(f"{subject}: {str(exc)[:100]}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(exc)[:300], "imported": 0})

    return {"imported": imported, "skipped": skipped, "errors": errors[:10]}


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
