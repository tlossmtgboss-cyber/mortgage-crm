"""
Inbound Calendar Sync
=====================
Receives webhook notifications from Google Calendar and Microsoft Outlook
when events are created, updated, or deleted externally, and syncs changes
back to the Smart Calendar (scheduler_appointments table).

Google Calendar uses push notifications via a "watch" channel:
  https://developers.google.com/calendar/api/guides/push

Microsoft Graph uses subscription webhooks:
  https://learn.microsoft.com/en-us/graph/webhooks

This module provides:

Endpoints (public, no auth -- verified by provider-specific headers/tokens):
  POST /calendar/sync/google/webhook      Receive Google Calendar push notification
  POST /calendar/sync/outlook/webhook     Receive Microsoft Graph change notification
  POST /calendar/sync/google/register     Register a watch channel (authenticated)
  POST /calendar/sync/outlook/register    Register an Outlook subscription (authenticated)

Sync helper functions:
  _process_google_changes()       Fetch changed events and apply to local appointments
  _process_outlook_notification() Fetch changed event and apply to local appointments
  _sync_external_event_to_local() Create/update/delete local appointment from external data
  _compute_event_fingerprint()    Detect meaningful changes (prevent echo loops)
  _resolve_conflict()             Handle concurrent local + remote modifications
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy.orm import Session

from db import get_db
from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Calendar Sync Inbound"])


# ============================================================================
# WEBHOOK TOKEN SIGNING — prevents spoofed webhook requests
# ============================================================================

def _get_webhook_signing_key() -> bytes:
    """Derive a signing key for calendar webhook tokens.

    Uses SECRET_KEY from environment. Falls back to a constant only in
    development -- production MUST have SECRET_KEY set.
    """
    secret = os.environ.get("SECRET_KEY", "dev-only-calendar-webhook-key")
    return hashlib.sha256(f"calendar-sync:{secret}".encode()).digest()


def _sign_channel_token(org_id: int, user_id: int) -> str:
    """Create an HMAC-signed channel token: 'org_id:user_id:signature'.

    The signature prevents attackers from forging webhook requests with
    guessed org_id:user_id values.
    """
    payload = f"{org_id}:{user_id}"
    sig = hmac.new(_get_webhook_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def _verify_channel_token(token: str) -> tuple[int | None, int | None, bool]:
    """Verify an HMAC-signed channel token.

    Returns (org_id, user_id, is_valid).
    Accepts legacy unsigned 'org_id:user_id' tokens with a warning.
    """
    if not token:
        return None, None, False

    parts = token.split(":")
    try:
        org_id = int(parts[0])
        user_id = int(parts[1]) if len(parts) > 1 else None
    except (ValueError, IndexError):
        return None, None, False

    if len(parts) == 3 and user_id is not None:
        # Signed token — verify HMAC
        expected_sig = hmac.new(
            _get_webhook_signing_key(),
            f"{org_id}:{user_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        is_valid = hmac.compare_digest(parts[2], expected_sig)
        if not is_valid:
            logger.warning("Calendar webhook: invalid HMAC signature in channel token")
        return org_id, user_id, is_valid

    # Legacy unsigned token — reject (NC4: unsigned tokens are a spoofing risk)
    logger.error(
        "Calendar webhook: unsigned channel token rejected. "
        "Re-register the watch channel to get a signed token."
    )
    return org_id, user_id, False


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class WatchChannelRegisterRequest(BaseModel):
    """Request to register a Google Calendar watch channel."""
    calendar_id: str = Field(default="primary", description="Google Calendar ID to watch")
    ttl_seconds: int = Field(
        default=604800,
        ge=3600,
        le=2592000,
        description="Channel TTL in seconds (default 7 days, max 30 days)",
    )


class OutlookSubscriptionRegisterRequest(BaseModel):
    """Request to register a Microsoft Graph calendar subscription."""
    expiration_minutes: int = Field(
        default=4230,
        ge=60,
        le=4230,
        description="Subscription expiration in minutes (max ~3 days for calendars)",
    )


class SyncStatusResponse(BaseModel):
    """Response for sync status queries."""
    provider: str
    channel_active: bool
    last_sync_at: Optional[str] = None
    events_synced: int = 0
    errors: int = 0


# ============================================================================
# GOOGLE CALENDAR WEBHOOK (PUBLIC -- no auth, verified by headers)
# ============================================================================

@router.post("/calendar/sync/google/webhook")
async def google_calendar_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Google Calendar push notification.

    Google sends a POST when calendar events change. The notification itself
    does not contain event data -- it signals that we need to call the
    Calendar API to fetch changes using a sync token.

    Headers from Google:
      X-Goog-Channel-ID:     The channel UUID we registered
      X-Goog-Resource-ID:    Opaque resource ID from Google
      X-Goog-Resource-State: "sync" (initial), "exists" (change), "not_exists" (deleted)
      X-Goog-Message-Number: Incrementing message counter
      X-Goog-Channel-Token:  Our custom token (org_id:user_id) for routing

    See: https://developers.google.com/calendar/api/guides/push
    """
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    channel_token = request.headers.get("X-Goog-Channel-Token")
    message_number = request.headers.get("X-Goog-Message-Number")

    if not channel_id or not resource_state:
        logger.warning("Google Calendar webhook: missing required headers")
        raise HTTPException(status_code=400, detail="Missing required Google headers")

    # Initial sync confirmation -- Google sends this when the channel is first created.
    # Just acknowledge it.
    if resource_state == "sync":
        logger.info(
            "Google Calendar watch channel confirmed: channel=%s resource=%s",
            channel_id, resource_id,
        )
        return {"status": "sync_confirmed"}

    # Verify the HMAC-signed channel token to prevent spoofed requests.
    # Format: "org_id:user_id:hmac_signature" (set when registering the watch channel).
    organization_id, user_id, token_valid = _verify_channel_token(channel_token)
    if not token_valid:
        logger.warning("Google Calendar webhook: rejected — invalid channel token")
        raise HTTPException(status_code=403, detail="Invalid channel token")

    logger.info(
        "Google Calendar webhook received: channel=%s state=%s org=%s user=%s msg=%s",
        channel_id, resource_state, organization_id, user_id, message_number,
    )

    if resource_state in ("exists", "not_exists"):
        # Process the change notification. The actual event data must be fetched
        # from the Google Calendar API using the sync token stored when we
        # registered the watch channel.
        try:
            sync_result = await _process_google_changes(
                db=db,
                channel_id=channel_id,
                resource_id=resource_id,
                organization_id=organization_id,
                user_id=user_id,
                resource_state=resource_state,
            )
            return {
                "status": "processed",
                "events_processed": sync_result.get("events_processed", 0),
                "errors": sync_result.get("errors", 0),
            }
        except Exception as e:
            logger.exception(
                "Google Calendar webhook processing failed: channel=%s error=%s",
                channel_id, e,
            )
            # Return 200 to prevent Google from retrying on app-level errors.
            # Google retries on 5xx and will eventually stop the channel.
            return {"status": "error", "message": str(e)}

    # Unknown state -- acknowledge to prevent retries
    logger.warning("Google Calendar webhook: unknown state=%s", resource_state)
    return {"status": "ignored", "reason": f"unknown state: {resource_state}"}


# ============================================================================
# OUTLOOK WEBHOOK (PUBLIC -- no auth, verified by validation token)
# ============================================================================

@router.post("/calendar/sync/outlook/webhook")
async def outlook_calendar_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Microsoft Graph change notification for calendar events.

    Microsoft Graph has two request patterns for this endpoint:

    1. Validation request: When a subscription is first created, Graph sends a
       POST with a `validationToken` query parameter. We must echo the token
       back as plain text with Content-Type: text/plain.

    2. Change notification: Graph sends a JSON body with a `value` array
       containing one or more change notifications. Each notification includes
       the resource path and change type but NOT the event data -- we must
       call the Graph API to fetch the changed event.

    See: https://learn.microsoft.com/en-us/graph/webhooks
    """
    # Handle validation request (Microsoft sends this when creating a subscription)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("Outlook webhook validation request received")
        return Response(
            content=validation_token,
            media_type="text/plain",
            status_code=200,
        )

    # Parse the change notification body
    try:
        body = await request.json()
    except Exception as e:
        logger.warning("Outlook webhook: invalid JSON body: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    notifications = body.get("value", [])
    if not notifications:
        logger.debug("Outlook webhook: empty notification list")
        return {"status": "ok", "events_processed": 0}

    total_processed = 0
    total_errors = 0

    for notification in notifications:
        resource = notification.get("resource", "")
        change_type = notification.get("changeType", "")
        subscription_id = notification.get("subscriptionId", "")
        client_state = notification.get("clientState", "")

        # Verify the client state HMAC signature and extract org/user IDs
        verified_org_id, verified_user_id, state_valid = _verify_channel_token(client_state)
        if not state_valid:
            logger.warning(
                "Outlook webhook: rejected notification with invalid clientState "
                "subscription=%s", subscription_id,
            )
            total_errors += 1
            continue

        logger.info(
            "Outlook webhook notification: subscription=%s change=%s resource=%s",
            subscription_id, change_type, resource,
        )

        try:
            sync_result = await _process_outlook_notification(
                db=db,
                resource=resource,
                change_type=change_type,
                subscription_id=subscription_id,
                client_state=client_state,
                verified_org_id=verified_org_id,
                verified_user_id=verified_user_id,
            )
            total_processed += sync_result.get("events_processed", 0)
            total_errors += sync_result.get("errors", 0)
        except Exception as e:
            logger.exception(
                "Outlook webhook processing failed: subscription=%s error=%s",
                subscription_id, e,
            )
            total_errors += 1

    return {
        "status": "processed",
        "events_processed": total_processed,
        "errors": total_errors,
    }


# ============================================================================
# WATCH CHANNEL REGISTRATION (AUTHENTICATED)
# ============================================================================

@router.post("/calendar/sync/google/register")
async def register_google_watch_channel(
    body: WatchChannelRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Register a Google Calendar watch channel for push notifications.

    Creates a watch channel via the Google Calendar API so that changes to the
    user's calendar trigger POST requests to our webhook endpoint.
    Requires the user to have connected their Google Calendar (valid OAuth tokens).
    """
    import uuid

    org_id = _get_org_id(current_user)
    user_id = getattr(current_user, "id", None)

    # Generate a unique channel ID and HMAC-signed channel token
    channel_id = str(uuid.uuid4())
    channel_token = _sign_channel_token(org_id, user_id)

    # Build the webhook URL
    # Use the API domain from env, falling back to the request host
    api_domain = os.environ.get("API_DOMAIN", "api.perenniaai.com")
    webhook_url = f"https://{api_domain}/api/v1/scheduler/calendar/sync/google/webhook"

    try:
        from integrations.google_calendar_service import google_calendar_client

        # Get user's Google Calendar credentials
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator
        orchestrator = CalendarSyncOrchestrator()
        providers = orchestrator._get_user_providers(db, current_user)
        google_creds = None
        for name, creds in providers:
            if name == "google":
                google_creds = creds
                break

        if not google_creds:
            raise HTTPException(
                status_code=400,
                detail="Google Calendar not connected. Connect it in Calendar Settings first.",
            )

        access_token = google_creds.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No valid Google access token")

        # Register the watch channel via Google Calendar API
        watch_body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
            "params": {
                "ttl": str(body.ttl_seconds),
            },
        }

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{body.calendar_id}/events/watch",
                json=watch_body,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code not in (200, 201):
            error_detail = resp.text[:500]
            logger.error(
                "Google watch channel registration failed: status=%d body=%s",
                resp.status_code, error_detail,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Google Calendar API error: {resp.status_code}",
            )

        result = resp.json()

        _audit_log(
            db=db,
            organization_id=org_id,
            user_id=user_id,
            action="google_watch_registered",
            entity_type="calendar_sync",
            entity_id=None,
            changes={
                "channel_id": channel_id,
                "resource_id": result.get("resourceId"),
                "expiration": result.get("expiration"),
            },
        )

        logger.info(
            "Google watch channel registered: channel=%s user=%s org=%s",
            channel_id, user_id, org_id,
        )

        return {
            "status": "registered",
            "channel_id": channel_id,
            "resource_id": result.get("resourceId"),
            "expiration": result.get("expiration"),
            "webhook_url": webhook_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to register Google watch channel: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register watch channel")


@router.post("/calendar/sync/outlook/register")
async def register_outlook_subscription(
    body: OutlookSubscriptionRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Register a Microsoft Graph subscription for calendar change notifications.

    Creates a subscription via the Graph API so that calendar changes trigger
    POST requests to our webhook endpoint.
    Requires the user to have connected their Microsoft/Outlook account.
    """
    import uuid

    org_id = _get_org_id(current_user)
    user_id = getattr(current_user, "id", None)

    # Build webhook URL
    api_domain = os.environ.get("API_DOMAIN", "api.perenniaai.com")
    webhook_url = f"https://{api_domain}/api/v1/scheduler/calendar/sync/outlook/webhook"

    # Client state for verification — HMAC-signed so we can verify
    # that incoming notifications actually came via our subscription
    client_state = _sign_channel_token(org_id, user_id)

    try:
        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator
        orchestrator = CalendarSyncOrchestrator()
        providers = orchestrator._get_user_providers(db, current_user)
        outlook_creds = None
        for name, creds in providers:
            if name == "outlook":
                outlook_creds = creds
                break

        if not outlook_creds:
            raise HTTPException(
                status_code=400,
                detail="Microsoft/Outlook calendar not connected. Connect it in Calendar Settings first.",
            )

        access_token = outlook_creds.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No valid Outlook access token")

        # Calculate expiration datetime
        from datetime import timedelta
        expiration = datetime.now(timezone.utc) + timedelta(minutes=body.expiration_minutes)

        subscription_body = {
            "changeType": "created,updated,deleted",
            "notificationUrl": webhook_url,
            "resource": "me/events",
            "expirationDateTime": expiration.isoformat(),
            "clientState": client_state,
        }

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/subscriptions",
                json=subscription_body,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code not in (200, 201):
            error_detail = resp.text[:500]
            logger.error(
                "Outlook subscription registration failed: status=%d body=%s",
                resp.status_code, error_detail,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Microsoft Graph API error: {resp.status_code}",
            )

        result = resp.json()

        _audit_log(
            db=db,
            organization_id=org_id,
            user_id=user_id,
            action="outlook_subscription_registered",
            entity_type="calendar_sync",
            entity_id=None,
            changes={
                "subscription_id": result.get("id"),
                "expiration": result.get("expirationDateTime"),
            },
        )

        logger.info(
            "Outlook subscription registered: subscription=%s user=%s org=%s",
            result.get("id"), user_id, org_id,
        )

        return {
            "status": "registered",
            "subscription_id": result.get("id"),
            "expiration": result.get("expirationDateTime"),
            "webhook_url": webhook_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to register Outlook subscription: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register subscription")


# ============================================================================
# SYNC PROCESSING HELPERS
# ============================================================================

import os


async def _process_google_changes(
    db: Session,
    channel_id: str,
    resource_id: str,
    organization_id: Optional[int],
    user_id: Optional[int],
    resource_state: str,
) -> Dict[str, Any]:
    """
    Fetch changed events from Google Calendar API and sync to local appointments.

    Google push notifications tell us THAT something changed but not WHAT changed.
    We must call the events.list API with a syncToken to get incremental changes.

    Returns dict with events_processed and errors counts.
    """
    from database.models.calendar_event_map import CalendarEventMap

    events_processed = 0
    errors = 0

    if not user_id or not organization_id:
        logger.warning(
            "Google sync: missing user_id or org_id, cannot process. "
            "channel=%s", channel_id,
        )
        return {"events_processed": 0, "errors": 1}

    try:
        # Look up user credentials
        from database.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning("Google sync: user %s not found", user_id)
            return {"events_processed": 0, "errors": 1}

        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator
        orchestrator = CalendarSyncOrchestrator()
        providers = orchestrator._get_user_providers(db, user)
        google_creds = None
        for name, creds in providers:
            if name == "google":
                google_creds = creds
                break

        if not google_creds or not google_creds.get("access_token"):
            logger.warning("Google sync: no credentials for user %s", user_id)
            return {"events_processed": 0, "errors": 1}

        # Fetch recent events from Google Calendar (incremental sync)
        from integrations.google_calendar_service import google_calendar_client
        from services.calendar_providers.google import GoogleCalendarProvider

        provider = GoogleCalendarProvider()
        access_token = await provider._ensure_valid_token(google_creds)
        if not access_token:
            logger.warning("Google sync: could not obtain valid token for user %s", user_id)
            return {"events_processed": 0, "errors": 1}

        # Fetch recently updated events (last 5 minutes window to catch the change)
        from datetime import timedelta
        time_min = datetime.now(timezone.utc) - timedelta(minutes=5)

        result = await google_calendar_client.list_events(
            access_token=access_token,
            time_min=time_min,
            max_results=50,
        )

        if not result or "items" not in result:
            logger.debug("Google sync: no events returned for user %s", user_id)
            return {"events_processed": 0, "errors": 0}

        for event in result["items"]:
            try:
                external_id = event.get("id", "")
                event_status = event.get("status", "confirmed")

                sync_result = await _sync_external_event_to_local(
                    db=db,
                    provider="google",
                    external_id=external_id,
                    external_event=event,
                    event_status=event_status,
                    organization_id=organization_id,
                    user_id=user_id,
                )

                if sync_result.get("action") != "skipped":
                    events_processed += 1

            except Exception as e:
                logger.exception(
                    "Google sync: failed to process event %s: %s",
                    event.get("id"), e,
                )
                errors += 1

    except Exception as e:
        logger.exception("Google sync: unexpected error: %s", e)
        errors += 1

    logger.info(
        "Google sync complete: channel=%s processed=%d errors=%d",
        channel_id, events_processed, errors,
    )
    return {"events_processed": events_processed, "errors": errors}


async def _process_outlook_notification(
    db: Session,
    resource: str,
    change_type: str,
    subscription_id: str,
    client_state: str,
    verified_org_id: int = None,
    verified_user_id: int = None,
) -> Dict[str, Any]:
    """
    Process a single Microsoft Graph change notification.

    The notification tells us the resource path (e.g., "me/events/{event_id}")
    and the change type (created, updated, deleted). We must call the Graph API
    to fetch the actual event data.

    Returns dict with events_processed and errors counts.
    """
    from database.models.calendar_event_map import CalendarEventMap

    events_processed = 0
    errors = 0

    # Use org_id and user_id from verified HMAC token (passed by caller)
    organization_id = verified_org_id
    user_id = verified_user_id

    if not user_id or not organization_id:
        logger.warning(
            "Outlook sync: cannot identify user from clientState=%s", client_state,
        )
        return {"events_processed": 0, "errors": 1}

    try:
        # Look up user credentials
        from database.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning("Outlook sync: user %s not found", user_id)
            return {"events_processed": 0, "errors": 1}

        from services.calendar_sync_orchestrator import CalendarSyncOrchestrator
        orchestrator = CalendarSyncOrchestrator()
        providers = orchestrator._get_user_providers(db, user)
        outlook_creds = None
        for name, creds in providers:
            if name == "outlook":
                outlook_creds = creds
                break

        if not outlook_creds or not outlook_creds.get("access_token"):
            logger.warning("Outlook sync: no credentials for user %s", user_id)
            return {"events_processed": 0, "errors": 1}

        access_token = outlook_creds["access_token"]

        if change_type == "deleted":
            # For deletions, the resource is gone -- we just need the event ID
            # Resource format: "me/events/{event_id}" or "Users/{user_id}/Events/{event_id}"
            external_id = resource.split("/")[-1] if "/" in resource else resource
            sync_result = await _sync_external_event_to_local(
                db=db,
                provider="outlook",
                external_id=external_id,
                external_event=None,
                event_status="cancelled",
                organization_id=organization_id,
                user_id=user_id,
            )
            if sync_result.get("action") != "skipped":
                events_processed += 1
        else:
            # Fetch the event from Graph API
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"https://graph.microsoft.com/v1.0/{resource}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            if resp.status_code == 200:
                event = resp.json()
                external_id = event.get("id", resource.split("/")[-1])

                sync_result = await _sync_external_event_to_local(
                    db=db,
                    provider="outlook",
                    external_id=external_id,
                    external_event=event,
                    event_status="confirmed",
                    organization_id=organization_id,
                    user_id=user_id,
                )
                if sync_result.get("action") != "skipped":
                    events_processed += 1
            elif resp.status_code == 404:
                # Event was deleted between notification and our fetch
                external_id = resource.split("/")[-1] if "/" in resource else resource
                sync_result = await _sync_external_event_to_local(
                    db=db,
                    provider="outlook",
                    external_id=external_id,
                    external_event=None,
                    event_status="cancelled",
                    organization_id=organization_id,
                    user_id=user_id,
                )
                if sync_result.get("action") != "skipped":
                    events_processed += 1
            else:
                logger.warning(
                    "Outlook sync: failed to fetch event. resource=%s status=%d",
                    resource, resp.status_code,
                )
                errors += 1

    except Exception as e:
        logger.exception("Outlook sync: unexpected error: %s", e)
        errors += 1

    return {"events_processed": events_processed, "errors": errors}


# ============================================================================
# CORE SYNC LOGIC
# ============================================================================

async def _sync_external_event_to_local(
    db: Session,
    provider: str,
    external_id: str,
    external_event: Optional[Dict[str, Any]],
    event_status: str,
    organization_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """
    Create, update, or cancel a local appointment based on an external event change.

    This is the core bidirectional sync function. It:
    1. Looks up existing CalendarEventMap by (provider, external_id)
    2. If found: updates or cancels the linked Appointment
    3. If not found and event_status != cancelled: creates a new Appointment
    4. Uses fingerprint comparison to prevent echo loops (don't re-sync a
       change that we pushed outbound in the first place)

    Args:
        db: Database session
        provider: Calendar provider name ("google" or "outlook")
        external_id: The event ID in the external system
        external_event: The event data dict from the provider API (None for deletions)
        event_status: "confirmed", "cancelled", "tentative"
        organization_id: Tenant org ID
        user_id: The user who owns this calendar connection

    Returns:
        Dict with "action" key: "created", "updated", "cancelled", "skipped"
    """
    from database.models.calendar_event_map import CalendarEventMap
    from database.models.scheduler import Appointment, AppointmentStatus, AppointmentStatusHistory

    # Look up existing mapping
    existing_map = (
        db.query(CalendarEventMap)
        .filter(
            CalendarEventMap.provider == provider,
            CalendarEventMap.external_id == external_id,
        )
        .first()
    )

    # --- DELETION / CANCELLATION ---
    if event_status == "cancelled":
        if not existing_map or existing_map.sync_status == "deleted":
            return {"action": "skipped", "reason": "no local mapping for deleted event"}

        appointment = db.query(Appointment).filter(
            Appointment.id == existing_map.appointment_id,
        ).first()

        if appointment and appointment.status not in (
            AppointmentStatus.CANCELLED,
            AppointmentStatus.COMPLETED,
        ):
            # Cancel the local appointment
            old_status = str(appointment.status.value) if appointment.status else None
            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancelled_at = datetime.now(timezone.utc)
            appointment.cancellation_reason = f"Cancelled externally via {provider}"
            appointment.updated_at = datetime.now(timezone.utc)

            # Record status history
            history = AppointmentStatusHistory(
                organization_id=organization_id,
                appointment_id=appointment.id,
                previous_status=old_status,
                new_status=AppointmentStatus.CANCELLED.value,
                change_source=f"{provider}_sync",
                notes=f"Event cancelled in {provider.title()} Calendar",
            )
            db.add(history)

            existing_map.sync_status = "deleted"
            existing_map.updated_at = datetime.now(timezone.utc)
            db.flush()

            logger.info(
                "Inbound sync: cancelled appointment %d from %s event %s",
                appointment.id, provider, external_id,
            )
            return {"action": "cancelled", "appointment_id": appointment.id}

        return {"action": "skipped", "reason": "appointment already cancelled/completed"}

    # --- CREATE or UPDATE ---
    if external_event is None:
        return {"action": "skipped", "reason": "no event data"}

    # Normalize the external event into a standard format
    normalized = _normalize_external_event(provider, external_event)
    if not normalized:
        return {"action": "skipped", "reason": "could not normalize event"}

    # Compute fingerprint to detect echo loops
    new_fingerprint = _compute_event_fingerprint(normalized)

    if existing_map:
        # UPDATE existing appointment
        appointment = db.query(Appointment).filter(
            Appointment.id == existing_map.appointment_id,
        ).first()

        if not appointment:
            logger.warning(
                "Inbound sync: CalendarEventMap %d references missing appointment %d",
                existing_map.id, existing_map.appointment_id,
            )
            return {"action": "skipped", "reason": "appointment not found"}

        # Check for echo loop: if the fingerprint matches what we last synced OUT,
        # this notification is just Google/Outlook echoing our own outbound push.
        current_fingerprint = _compute_appointment_fingerprint(appointment)
        if new_fingerprint == current_fingerprint:
            logger.debug(
                "Inbound sync: skipping echo for appointment %d (fingerprint match)",
                appointment.id,
            )
            return {"action": "skipped", "reason": "echo_loop_detected"}

        # Check for conflict: both local and remote modified since last sync
        conflict = _resolve_conflict(
            appointment=appointment,
            external_event=normalized,
            last_synced_at=existing_map.synced_at,
        )

        if conflict == "skip_inbound":
            logger.info(
                "Inbound sync: conflict resolved in favor of local for appointment %d",
                appointment.id,
            )
            return {"action": "skipped", "reason": "conflict_local_wins"}

        # Apply changes from external event
        _apply_external_changes(appointment, normalized)

        existing_map.synced_at = datetime.now(timezone.utc)
        existing_map.sync_status = "synced"
        existing_map.last_error = None
        existing_map.updated_at = datetime.now(timezone.utc)

        # Record status history for the update
        history = AppointmentStatusHistory(
            organization_id=organization_id,
            appointment_id=appointment.id,
            previous_status=str(appointment.status.value) if appointment.status else None,
            new_status=str(appointment.status.value) if appointment.status else None,
            change_source=f"{provider}_sync",
            notes=f"Updated from {provider.title()} Calendar",
        )
        db.add(history)
        db.flush()

        logger.info(
            "Inbound sync: updated appointment %d from %s event %s",
            appointment.id, provider, external_id,
        )
        return {"action": "updated", "appointment_id": appointment.id}

    else:
        # CREATE new appointment from external event
        appointment = Appointment(
            organization_id=organization_id,
            assigned_user_id=user_id,
            title=normalized.get("title", "External Event"),
            description=normalized.get("description", ""),
            scheduled_start=normalized["start"],
            scheduled_end=normalized["end"],
            duration_minutes=int(
                (normalized["end"] - normalized["start"]).total_seconds() / 60
            ),
            timezone=normalized.get("timezone", "UTC"),
            location=normalized.get("location"),
            status=AppointmentStatus.BOOKED,
            external_id=external_id,
            external_source=provider,
        )
        db.add(appointment)
        db.flush()  # Get the appointment ID

        # Create the CalendarEventMap linking
        event_map = CalendarEventMap(
            organization_id=organization_id,
            appointment_id=appointment.id,
            provider=provider,
            external_id=external_id,
            external_link=normalized.get("link"),
            sync_status="synced",
            synced_at=datetime.now(timezone.utc),
        )
        db.add(event_map)

        # Record creation in status history
        history = AppointmentStatusHistory(
            organization_id=organization_id,
            appointment_id=appointment.id,
            previous_status=None,
            new_status=AppointmentStatus.BOOKED.value,
            change_source=f"{provider}_sync",
            notes=f"Created from {provider.title()} Calendar event",
        )
        db.add(history)
        db.flush()

        logger.info(
            "Inbound sync: created appointment %d from %s event %s",
            appointment.id, provider, external_id,
        )
        return {"action": "created", "appointment_id": appointment.id}


# ============================================================================
# NORMALIZATION HELPERS
# ============================================================================

def _normalize_external_event(
    provider: str,
    event: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Normalize a provider-specific event dict into a standard format.

    Returns None if the event cannot be parsed (e.g., missing required fields).

    Standard format:
        {
            "title": str,
            "description": str,
            "start": datetime (UTC),
            "end": datetime (UTC),
            "timezone": str,
            "location": str or None,
            "attendees": list of email strings,
            "link": str or None (web URL to view the event),
        }
    """
    if provider == "google":
        return _normalize_google_event(event)
    elif provider == "outlook":
        return _normalize_outlook_event(event)
    else:
        logger.warning("Unknown provider for normalization: %s", provider)
        return None


def _normalize_google_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a Google Calendar event."""
    start_dict = event.get("start", {})
    end_dict = event.get("end", {})

    start = _parse_google_datetime(start_dict)
    end = _parse_google_datetime(end_dict)

    if not start or not end:
        return None

    attendees = []
    for attendee in event.get("attendees", []):
        email = attendee.get("email")
        if email:
            attendees.append(email)

    return {
        "title": event.get("summary", "Untitled Event"),
        "description": event.get("description", ""),
        "start": start,
        "end": end,
        "timezone": start_dict.get("timeZone", "UTC"),
        "location": event.get("location"),
        "attendees": attendees,
        "link": event.get("htmlLink"),
    }


def _normalize_outlook_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a Microsoft Graph calendar event."""
    start_dict = event.get("start", {})
    end_dict = event.get("end", {})

    start = _parse_outlook_datetime(start_dict)
    end = _parse_outlook_datetime(end_dict)

    if not start or not end:
        return None

    attendees = []
    for attendee in event.get("attendees", []):
        email_addr = attendee.get("emailAddress", {})
        email = email_addr.get("address")
        if email:
            attendees.append(email)

    return {
        "title": event.get("subject", "Untitled Event"),
        "description": event.get("bodyPreview", "") or (
            event.get("body", {}).get("content", "")
        ),
        "start": start,
        "end": end,
        "timezone": start_dict.get("timeZone", "UTC"),
        "location": (
            event.get("location", {}).get("displayName")
            if isinstance(event.get("location"), dict) else event.get("location")
        ),
        "attendees": attendees,
        "link": event.get("webLink"),
    }


def _parse_google_datetime(dt_dict: Dict[str, Any]) -> Optional[datetime]:
    """Parse Google Calendar start/end dict into a UTC datetime."""
    if not dt_dict:
        return None
    if "dateTime" in dt_dict:
        try:
            return datetime.fromisoformat(
                dt_dict["dateTime"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            return None
    if "date" in dt_dict:
        try:
            return datetime.fromisoformat(dt_dict["date"] + "T00:00:00+00:00")
        except (ValueError, TypeError):
            return None
    return None


def _parse_outlook_datetime(dt_dict: Dict[str, Any]) -> Optional[datetime]:
    """Parse Microsoft Graph start/end dict into a UTC datetime."""
    if not dt_dict:
        return None
    date_str = dt_dict.get("dateTime")
    if not date_str:
        return None
    try:
        tz_name = dt_dict.get("timeZone", "UTC")
        # Graph returns datetimes in the event's timezone without offset
        # We parse and attach UTC if timezone is UTC, otherwise treat as naive
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            if tz_name == "UTC":
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Best effort: try pytz conversion
                try:
                    import pytz
                    tz = pytz.timezone(tz_name)
                    dt = tz.localize(dt).astimezone(pytz.utc)
                except Exception as e:
                    logger.debug(f"Failed pytz conversion for tz '{tz_name}', falling back to UTC: {e}")
                    dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ============================================================================
# FINGERPRINTING (ECHO LOOP PREVENTION)
# ============================================================================

def _compute_event_fingerprint(normalized_event: Dict[str, Any]) -> str:
    """
    Compute a SHA-256 fingerprint of the key scheduling fields of a normalized event.

    Used to detect whether an inbound change notification is an echo of a change
    we recently pushed outbound (preventing infinite sync loops).
    """
    parts = [
        (normalized_event.get("title") or "").strip().lower(),
        normalized_event["start"].strftime("%Y-%m-%dT%H:%M:%SZ") if normalized_event.get("start") else "",
        normalized_event["end"].strftime("%Y-%m-%dT%H:%M:%SZ") if normalized_event.get("end") else "",
        (normalized_event.get("location") or "").strip().lower(),
    ]
    concatenated = "|".join(parts)
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def _compute_appointment_fingerprint(appointment) -> str:
    """
    Compute a SHA-256 fingerprint of the key scheduling fields of a local Appointment.

    The fingerprint format must match _compute_event_fingerprint so that
    comparison detects whether the external event matches our local state.
    """
    title = (getattr(appointment, "title", "") or "").strip().lower()
    start = getattr(appointment, "scheduled_start", None)
    end = getattr(appointment, "scheduled_end", None)
    location = (getattr(appointment, "location", "") or "").strip().lower()

    parts = [
        title,
        start.strftime("%Y-%m-%dT%H:%M:%SZ") if start else "",
        end.strftime("%Y-%m-%dT%H:%M:%SZ") if end else "",
        location,
    ]
    concatenated = "|".join(parts)
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


# ============================================================================
# CONFLICT RESOLUTION
# ============================================================================

def _resolve_conflict(
    appointment,
    external_event: Dict[str, Any],
    last_synced_at: Optional[datetime],
) -> str:
    """
    Determine whether to apply inbound changes when both local and remote
    have been modified since the last sync.

    Conflict resolution strategy (last-write-wins by default):
    - If local was modified after last sync AND remote was also modified:
      compare timestamps and let the most recent modification win.
    - If only remote was modified: apply inbound ("apply_inbound")
    - If only local was modified: skip inbound ("skip_inbound")

    Returns:
        "apply_inbound" or "skip_inbound"
    """
    if not last_synced_at:
        # No previous sync -- always apply inbound
        return "apply_inbound"

    local_updated = getattr(appointment, "updated_at", None)

    # If local hasn't been modified since last sync, apply inbound
    if not local_updated or local_updated <= last_synced_at:
        return "apply_inbound"

    # Both sides modified -- last-write-wins
    # We don't have a reliable "remote updated_at" from the normalized event,
    # so we default to applying inbound (the external change is happening NOW,
    # which is after our last sync).
    return "apply_inbound"


# ============================================================================
# APPLY CHANGES HELPER
# ============================================================================

def _apply_external_changes(
    appointment,
    normalized_event: Dict[str, Any],
) -> None:
    """
    Apply normalized external event fields to a local Appointment ORM instance.

    Only updates fields that have actually changed to minimize unnecessary writes.
    """
    now = datetime.now(timezone.utc)

    new_title = normalized_event.get("title", "")
    if new_title and new_title != appointment.title:
        appointment.title = new_title

    new_desc = normalized_event.get("description", "")
    if new_desc != (appointment.description or ""):
        appointment.description = new_desc

    new_start = normalized_event.get("start")
    if new_start and new_start != appointment.scheduled_start:
        appointment.scheduled_start = new_start

    new_end = normalized_event.get("end")
    if new_end and new_end != appointment.scheduled_end:
        appointment.scheduled_end = new_end

    if new_start and new_end:
        new_duration = int((new_end - new_start).total_seconds() / 60)
        if new_duration != appointment.duration_minutes:
            appointment.duration_minutes = new_duration

    new_tz = normalized_event.get("timezone")
    if new_tz and new_tz != appointment.timezone:
        appointment.timezone = new_tz

    new_location = normalized_event.get("location")
    if new_location != appointment.location:
        appointment.location = new_location

    appointment.last_synced_at = now
    appointment.updated_at = now
