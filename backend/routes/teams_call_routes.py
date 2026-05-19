"""
Teams Inbound Call Notification Routes
=======================================
WebSocket endpoint that pushes real-time caller info to the CRM frontend
when an inbound Teams call matches a CRM contact.

1. POST /api/v1/teams/calls/inbound — webhook from Graph change notifications
2. WS   /ws/calls/inbound            — per-user WebSocket for push notifications
3. POST /api/v1/teams/calls/lookup   — authenticated manual phone lookup

Webhook verification: uses HMAC clientState matching against the Graph
subscription record, consistent with the existing Microsoft 365 webhook
handler in integrations/microsoft365/webhooks.py.

Graph notification format: The POST body follows the standard Graph change
notification envelope ({value: [{subscriptionId, clientState, resourceData, ...}]}).
For communications/callRecords, resourceData contains @odata.type and id.
We also accept a simplified direct-push format ({caller_phone, target_user_id, ...})
for internal use and Power Automate flows.
"""

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from db import get_async_db
from routes.auth_deps import current_user_flexible_dep
from utils.websocket_auth import authenticate_websocket_post_connect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teams Calls"])

TEAMS_WEBHOOK_SECRET = os.getenv("TEAMS_WEBHOOK_SECRET", "")


def _normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))[-10:]


async def _lookup_contact_by_phone(db: AsyncSession, phone: str, organization_id: int) -> Optional[Dict[str, Any]]:
    """Search leads and client_files for a matching phone number."""
    phone_clean = _normalize_phone(phone)
    if not phone_clean:
        return None

    suffixes = [phone_clean, f"+1{phone_clean}", f"1{phone_clean}"]

    result = await db.execute(
        text("""
            SELECT id, name, first_name, last_name, email, phone, stage,
                   owner_id, organization_id
            FROM leads
            WHERE organization_id = :org_id
              AND (
                  REPLACE(REPLACE(REPLACE(REPLACE(phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :suffix
                  OR phone = ANY(:suffixes)
              )
            LIMIT 1
        """),
        {
            "org_id": organization_id,
            "suffix": f"%{phone_clean}",
            "suffixes": suffixes,
        },
    )
    row = result.fetchone()
    if row:
        return {
            "match_type": "lead",
            "id": row[0],
            "name": row[1] or f"{row[2] or ''} {row[3] or ''}".strip(),
            "first_name": row[2],
            "last_name": row[3],
            "email": row[4],
            "phone": row[5],
            "stage": row[6],
            "owner_id": row[7],
            "profile_url": f"/leads/{row[0]}",
        }

    cf_result = await db.execute(
        text("""
            SELECT cf.id, cf.first_name, cf.last_name, cf.primary_email,
                   cf.primary_phone, cf.lifecycle_stage, cf.assigned_loan_officer_id
            FROM client_files cf
            WHERE cf.organization_id = :org_id
              AND (
                  REPLACE(REPLACE(REPLACE(REPLACE(cf.primary_phone, '-', ''), '(', ''), ')', ''), ' ', '') LIKE :suffix
                  OR cf.primary_phone = ANY(:suffixes)
              )
            LIMIT 1
        """),
        {
            "org_id": organization_id,
            "suffix": f"%{phone_clean}",
            "suffixes": suffixes,
        },
    )
    cf_row = cf_result.fetchone()
    if cf_row:
        return {
            "match_type": "client_file",
            "id": str(cf_row[0]),
            "name": f"{cf_row[1] or ''} {cf_row[2] or ''}".strip(),
            "email": cf_row[3],
            "phone": cf_row[4],
            "stage": cf_row[5],
            "owner_id": cf_row[6],
            "profile_url": f"/client-file/{cf_row[0]}",
        }

    return None


class CallConnectionManager:
    """Manages per-user WebSocket connections for inbound call notifications."""

    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)
        logger.info("Call WS connected for user %s", user_id)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.connections:
            if websocket in self.connections[user_id]:
                self.connections[user_id].remove(websocket)
            if not self.connections[user_id]:
                del self.connections[user_id]
        logger.info("Call WS disconnected for user %s", user_id)

    async def notify_user(self, user_id: int, data: Dict[str, Any]):
        conns = self.connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                dead.append(ws)
        for ws in dead:
            if ws in conns:
                conns.remove(ws)


call_manager = CallConnectionManager()


# ---------------------------------------------------------------------------
# Security: Token sent as first message after connect (not in URL query string)
# to avoid leaking JWT into server/proxy access logs and browser history.
# Backwards compatible: old clients with ?token= query param still work.
# ---------------------------------------------------------------------------
@router.websocket("/ws/calls/inbound")
async def ws_inbound_calls(websocket: WebSocket):
    """WebSocket endpoint for real-time inbound call notifications."""
    await websocket.accept()

    gen = get_db()
    auth_db = next(gen)
    try:
        user, error = await authenticate_websocket_post_connect(websocket, auth_db)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    if not user:
        await websocket.send_json({"type": "error", "message": error or "Unauthorized"})
        await websocket.close(code=4001, reason=error or "Unauthorized")
        return

    await call_manager.connect(websocket, user.id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        call_manager.disconnect(websocket, user.id)


def _verify_webhook_secret(request: Request, body: dict) -> bool:
    """Verify the webhook is authentic.

    Accepts either:
    - HMAC clientState in the Graph notification matching TEAMS_WEBHOOK_SECRET
    - X-Webhook-Secret header matching TEAMS_WEBHOOK_SECRET
    """
    if not TEAMS_WEBHOOK_SECRET:
        logger.warning("TEAMS_WEBHOOK_SECRET not configured — rejecting webhook")
        return False

    header_secret = request.headers.get("x-webhook-secret", "")
    if header_secret and hmac.compare_digest(header_secret, TEAMS_WEBHOOK_SECRET):
        return True

    notifications = body.get("value", [])
    for notif in notifications:
        client_state = notif.get("clientState", "")
        if client_state and hmac.compare_digest(client_state, TEAMS_WEBHOOK_SECRET):
            return True

    return False


@router.post("/api/v1/teams/calls/inbound")
async def handle_inbound_call(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Webhook endpoint for Teams/Graph inbound call notifications.
    Supports Graph subscription validation (responds to validationToken).
    Requires HMAC verification via clientState or X-Webhook-Secret header.
    """
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")

    try:
        body = await request.json()
    except Exception as _exc:  # noqa: BLE001
        return JSONResponse({"status": "invalid_body"}, status_code=400)

    if not _verify_webhook_secret(request, body):
        logger.warning("Teams call webhook failed verification")
        return JSONResponse({"status": "unauthorized"}, status_code=403)

    notifications = body.get("value", [body] if "caller_phone" in body else [])

    for notif in notifications:
        caller_phone = notif.get("caller_phone") or ""
        caller_name = notif.get("caller_display_name") or ""
        target_user_id = notif.get("target_user_id")
        target_email = notif.get("target_email")

        if not caller_phone and not caller_name:
            resource_data = notif.get("resourceData", {})
            caller_phone = resource_data.get("source", {}).get("identity", {}).get("phone", {}).get("id", "")
            caller_name = resource_data.get("source", {}).get("identity", {}).get("displayName", "")
            target_email = resource_data.get("targets", [{}])[0].get("identity", {}).get("user", {}).get("id", "")

        if not target_user_id and target_email:
            user_row = (await db.execute(
                text("SELECT id, organization_id FROM users WHERE email = :email LIMIT 1"),
                {"email": target_email},
            )).fetchone()
            if user_row:
                target_user_id = user_row[0]
                org_id = user_row[1]
            else:
                continue
        elif target_user_id:
            user_row = (await db.execute(
                text("SELECT organization_id FROM users WHERE id = :uid LIMIT 1"),
                {"uid": target_user_id},
            )).fetchone()
            org_id = user_row[0] if user_row else None
        else:
            continue

        if not org_id:
            continue

        contact = await _lookup_contact_by_phone(db, caller_phone, org_id)

        payload = {
            "type": "inbound_call",
            "caller_phone": caller_phone,
            "caller_display_name": caller_name,
            "call_id": notif.get("call_id") or notif.get("resourceData", {}).get("id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contact": contact,
        }

        await call_manager.notify_user(target_user_id, payload)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# C3 FIX: Authenticated lookup, org_id derived from user
# ---------------------------------------------------------------------------
@router.post("/api/v1/teams/calls/lookup")
async def lookup_caller(
    request: Request,
    current_user=Depends(current_user_flexible_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Manual phone lookup — requires authentication."""
    body = await request.json()
    phone = body.get("phone", "")

    org_id = None
    if isinstance(current_user, dict):
        org_id = current_user.get("organization_id")
    else:
        org_id = getattr(current_user, "organization_id", None)

    if not phone or not org_id:
        return {"contact": None}

    contact = await _lookup_contact_by_phone(db, phone, org_id)
    return {"contact": contact}


@router.post("/api/v1/teams/calls/simulate")
async def simulate_inbound_call(
    request: Request,
    current_user=Depends(current_user_flexible_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Simulate an inbound call to test the lightbox. Authenticated — pushes
    a notification to the current user's WebSocket connection."""
    body = await request.json()
    caller_phone = body.get("phone", "+15551234567")
    caller_name = body.get("name", "")

    user_id = None
    org_id = None
    if isinstance(current_user, dict):
        user_id = current_user.get("id")
        org_id = current_user.get("organization_id")
    else:
        user_id = getattr(current_user, "id", None)
        org_id = getattr(current_user, "organization_id", None)

    if not user_id:
        return JSONResponse({"error": "no user"}, status_code=401)

    contact = await _lookup_contact_by_phone(db, caller_phone, org_id) if org_id else None

    payload = {
        "type": "inbound_call",
        "caller_phone": caller_phone,
        "caller_display_name": caller_name or "Test Caller",
        "call_id": f"simulate-{datetime.now(timezone.utc).timestamp():.0f}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contact": contact,
    }

    await call_manager.notify_user(user_id, payload)
    return {"status": "sent", "payload": payload}
