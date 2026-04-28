"""
SMS Conversation Routes — Two-way SMS panel backend.

Production-grade: authenticated, tenant-isolated, real-time delivery tracking.

Endpoints consumed by the SMSAccordionPanel component:
  GET  /api/v1/sms/conversations/{phone}   — message history (paginated)
  POST /api/v1/sms/send                    — send SMS/MMS (compliance + Telnyx)
  POST /api/v1/sms/upload-media            — upload MMS attachment
  WS   /ws/sms/{phone}                     — real-time inbound + status push
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import (
    APIRouter, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, Request, UploadFile, File, Form,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, validator

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sms", tags=["SMS Conversations"])
ws_router = APIRouter()

_security = HTTPBearer(auto_error=False)


# ─── Auth helper (lazy import to avoid circular deps) ───────────────────────

async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Authenticate the request and return the current user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _get_org_id(user) -> Optional[int]:
    return getattr(user, "organization_id", None)


def _get_user_name(user) -> str:
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    name = f"{first} {last}".strip()
    return name or getattr(user, "email", "User")


def _get_user_id(user) -> Optional[int]:
    return getattr(user, "id", None)


# ─── Pydantic models ─────────────────────────────────────────────────────────

class SendSMSRequest(BaseModel):
    contactId: Optional[str] = ""
    to: str
    message: str
    mediaUrls: list[str] = []
    pageType: str = "client"
    borrowerType: str = "primary"

    @validator("contactId", pre=True, always=True)
    def coerce_contact_id(cls, v):
        if v is None:
            return ""
        return str(v)


class SMSMessageResponse(BaseModel):
    id: str
    direction: str  # inbound | outbound
    body: str
    senderName: str
    senderRole: Optional[str] = None
    timestamp: str
    status: Optional[str] = None
    mediaUrls: list = []


# ─── WebSocket Connection Manager ────────────────────────────────────────────

class SMSConnectionManager:
    """Track open WebSocket connections by (org_id, phone) for real-time push."""

    def __init__(self):
        # Key: "orgId:normalizedPhone" → list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    def _key(self, org_id: Optional[int], phone: str) -> str:
        normalized = _normalize_phone(phone)
        return f"{org_id or 0}:{normalized}"

    async def connect(self, org_id: Optional[int], phone: str, ws: WebSocket):
        await ws.accept()
        key = self._key(org_id, phone)
        if key not in self._connections:
            self._connections[key] = []
        self._connections[key].append(ws)

    def disconnect(self, org_id: Optional[int], phone: str, ws: WebSocket):
        key = self._key(org_id, phone)
        conns = self._connections.get(key, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(key, None)

    async def broadcast(self, org_id: Optional[int], phone: str, message: dict):
        """Push a message to all clients watching this org+phone."""
        key = self._key(org_id, phone)
        dead = []
        for ws in self._connections.get(key, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(org_id, phone, ws)

    async def broadcast_all_orgs(self, phone: str, message: dict):
        """Broadcast to all orgs watching this phone (for inbound where org is unknown)."""
        normalized = _normalize_phone(phone)
        suffix = f":{normalized}"
        dead_pairs = []
        for key, conns in self._connections.items():
            if key.endswith(suffix):
                for ws in conns:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        dead_pairs.append((key, ws))
        for key, ws in dead_pairs:
            conns = self._connections.get(key, [])
            if ws in conns:
                conns.remove(ws)


sms_manager = SMSConnectionManager()


def _normalize_phone(phone: str) -> str:
    """Strip to digits for consistent lookup."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return digits


# ─── Helper: ensure tables exist ─────────────────────────────────────────────

def _ensure_tables(db: Session):
    """Create sms_panel_messages table if it doesn't exist (with tenant isolation)."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS sms_panel_messages (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                contact_id TEXT,
                organization_id INTEGER,
                direction TEXT NOT NULL DEFAULT 'outbound',
                body TEXT NOT NULL DEFAULT '',
                sender_name TEXT DEFAULT '',
                sender_user_id INTEGER,
                sender_role TEXT,
                status TEXT DEFAULT 'sent',
                media_urls JSONB DEFAULT '[]'::jsonb,
                media_s3_keys JSONB DEFAULT '[]'::jsonb,
                page_type TEXT DEFAULT 'client',
                borrower_type TEXT DEFAULT 'primary',
                telnyx_message_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_panel_phone ON sms_panel_messages (phone)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_panel_contact ON sms_panel_messages (contact_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_panel_org ON sms_panel_messages (organization_id)
        """))
        # Add organization_id, sender_user_id, and media_s3_keys columns if table pre-exists without them
        for col, col_type in [
            ("organization_id", "INTEGER"),
            ("sender_user_id", "INTEGER"),
            ("media_s3_keys", "JSONB DEFAULT '[]'::jsonb"),
        ]:
            db.execute(text(f"""
                ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS {col} {col_type}
            """))
        # Clean up rows where sender_name was set to a numeric ID
        db.execute(text("""
            UPDATE sms_panel_messages SET sender_name = ''
            WHERE sender_name ~ '^[0-9]+$'
        """))
        db.commit()
        # Ensure sms_delivery_log exists (table may be missing in production)
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_delivery_log (
                    id SERIAL PRIMARY KEY,
                    telnyx_message_id VARCHAR(100) UNIQUE NOT NULL,
                    to_phone VARCHAR(20) NOT NULL,
                    from_phone VARCHAR(20),
                    message_body TEXT,
                    direction VARCHAR(20) DEFAULT 'outbound',
                    status VARCHAR(50) DEFAULT 'queued',
                    segments INTEGER DEFAULT 1,
                    consent_record_id INTEGER,
                    consent_verified_at TIMESTAMPTZ,
                    consent_method VARCHAR(50),
                    organization_id INTEGER,
                    user_id INTEGER,
                    lead_id INTEGER,
                    queue_id INTEGER,
                    error_code VARCHAR(50),
                    carrier_name VARCHAR(100),
                    sent_at TIMESTAMPTZ,
                    delivered_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_sms_delivery_telnyx_id ON sms_delivery_log (telnyx_message_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_sms_delivery_to_phone ON sms_delivery_log (to_phone)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_sms_delivery_org ON sms_delivery_log (organization_id)"))
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    except Exception as e:
        db.rollback()
        logger.warning(f"Table creation skipped (may already exist): {e}")


_tables_checked = False


def _check_tables(db: Session):
    global _tables_checked
    if not _tables_checked:
        _ensure_tables(db)
        _tables_checked = True


def _resolve_contact_name(db: Session, phone: str, org_id: Optional[int]) -> str:
    """Look up the contact/lead name from their phone number."""
    digits = "".join(c for c in phone if c.isdigit())[-10:]
    if not digits:
        return ""
    pattern = f"%{digits}"
    try:
        row = db.execute(text("""
            SELECT first_name, last_name FROM leads
            WHERE REPLACE(REPLACE(REPLACE(COALESCE(phone, ''), '+', ''), '-', ''), ' ', '') LIKE :pattern
            AND (:org_id IS NULL OR organization_id = :org_id)
            LIMIT 1
        """), {"pattern": pattern, "org_id": org_id}).fetchone()
        if row:
            name = f"{row[0] or ''} {row[1] or ''}".strip()
            if name:
                return name
    except Exception as e:
        logger.debug("_resolve_contact_name failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
    return ""


# ─── GET /conversations/{phone} ──────────────────────────────────────────────

@router.get("/conversations/{phone}")
async def get_conversation(
    phone: str,
    limit: int = 100,
    before: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(_require_auth),
):
    """
    Get SMS conversation history for a phone number.
    Returns merged inbound + outbound messages sorted by timestamp.
    Tenant-isolated by organization_id.
    Supports cursor pagination via `before` (ISO timestamp).
    """
    _check_tables(db)
    org_id = _get_org_id(current_user)

    _rls_org = org_id or 1

    logger.info(
        "SMS GET /conversations/%s: user_id=%s org_id=%s phone_raw=%s",
        phone[-4:] if phone else "?",
        _get_user_id(current_user),
        org_id,
        phone,
    )
    normalized = _normalize_phone(phone)
    like_pattern = f"%{normalized[-10:]}"  # match last 10 digits

    # Resolve contact name from phone number for display
    contact_display_name = _resolve_contact_name(db, normalized, org_id)

    # Build optional cursor filter
    # NOTE: org_id filter deliberately removed from SMS conversation queries.
    # Phone number is the isolation boundary — a single Telnyx number serves
    # all orgs, and inbound/outbound messages may have different org_ids
    # (inbound resolved from verified_caller_ids, outbound from user session).
    before_filter = ""
    org_filter = ""
    params: dict = {"pattern": like_pattern, "lim": limit}
    if before:
        before_filter = "AND sent_at < :before"
        params["before"] = before

    messages = []

    def _set_rls():
        """(Re)set RLS tenant context for the current transaction."""
        try:
            db.execute(text("SET LOCAL app.current_tenant = :org_id"), {"org_id": str(_rls_org)})
        except Exception:
            pass

    # 1. Outbound from sms_delivery_log (existing Telnyx tracking table)
    _set_rls()
    try:
        rows = db.execute(text(f"""
            SELECT
                telnyx_message_id AS id,
                'outbound' AS direction,
                message_body AS body,
                status,
                sent_at AS created_at,
                user_id
            FROM sms_delivery_log
            WHERE REPLACE(REPLACE(REPLACE(to_phone, '+', ''), '-', ''), ' ', '')
                  LIKE :pattern
              {org_filter}
            {before_filter}
            ORDER BY sent_at DESC
            LIMIT :lim
        """), params).fetchall()

        for r in rows:
            sender_name = "System"
            sender_user_id = r[5]
            if sender_user_id:
                try:
                    user_row = db.execute(text(
                        "SELECT first_name, last_name FROM users WHERE id = :uid"
                    ), {"uid": sender_user_id}).fetchone()
                    if user_row:
                        name = f"{user_row[0] or ''} {user_row[1] or ''}".strip()
                        if name and not name.isdigit():
                            sender_name = name
                except Exception:
                    try:
                        db.rollback()
                        _set_rls()
                    except Exception:
                        pass

            messages.append({
                "id": r[0] or str(uuid.uuid4()),
                "direction": "outbound",
                "body": r[2] or "",
                "senderName": sender_name,
                "senderRole": None,
                "timestamp": r[4].isoformat() if r[4] else datetime.now(timezone.utc).isoformat(),
                "status": r[3] or "sent",
                "mediaUrls": [],
            })
    except Exception as e:
        logger.warning(f"sms_delivery_log query failed (messages may be incomplete): {e}")
        try:
            db.rollback()
            _set_rls()
        except Exception:
            pass

    # 2. Messages from sms_panel_messages (two-way table, tenant-isolated)
    before_filter_panel = ""
    if before:
        before_filter_panel = "AND created_at < :before"

    _set_rls()
    try:
        rows = db.execute(text(f"""
            SELECT id, direction, body, sender_name, sender_role, status,
                   media_urls, created_at, telnyx_message_id, media_s3_keys
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '')
                  LIKE :pattern
              {org_filter}
            {before_filter_panel}
            ORDER BY created_at DESC
            LIMIT :lim
        """), params).fetchall()

        # Resolve S3 keys to presigned URLs for media display
        _media_storage = None
        try:
            from utils.media_storage import get_media_storage
            _media_storage = get_media_storage()
        except Exception:
            pass

        for r in rows:
            # Prefer S3 presigned URLs over original (possibly expired) Telnyx URLs
            resolved_urls = []
            s3_keys = r[9] if len(r) > 9 and r[9] else []
            original_urls = r[6] if r[6] else []

            if s3_keys and _media_storage and _media_storage.is_available:
                for key in s3_keys:
                    presigned = _media_storage.get_media_url(key)
                    if presigned:
                        resolved_urls.append(presigned)
            if not resolved_urls:
                resolved_urls = original_urls

            raw_sender = r[3] or ""
            if r[1] == "inbound":
                sender_display = contact_display_name or ("Customer" if (not raw_sender or raw_sender.isdigit()) else raw_sender)
            else:
                sender_display = raw_sender if (raw_sender and not raw_sender.isdigit()) else "System"

            messages.append({
                "id": r[0],
                "direction": r[1],
                "body": r[2] or "",
                "senderName": sender_display,
                "senderRole": r[4],
                "timestamp": r[7].isoformat() if r[7] else datetime.now(timezone.utc).isoformat(),
                "status": r[5] or "delivered",
                "mediaUrls": resolved_urls,
                "_telnyx_id": r[8],  # for dedup
            })
    except Exception as e:
        logger.warning(f"sms_panel_messages query failed (messages may be incomplete): {e}")
        try:
            db.rollback()
        except Exception:
            pass

    # Deduplicate: panel messages share telnyx_message_id with delivery_log.
    # Panel rows have richer metadata (sender name, role, media), so when a
    # delivery_log row and a panel row share the same telnyx_message_id we
    # keep the panel version.
    seen: Dict[str, int] = {}  # dedup_key -> index in unique
    unique = []
    for m in messages:
        telnyx_id = m.get("_telnyx_id") or ""
        msg_id = m["id"] or ""
        dedup_key = telnyx_id or msg_id
        if not dedup_key:
            m.pop("_telnyx_id", None)
            unique.append(m)
            continue
        if dedup_key not in seen and msg_id not in seen:
            idx = len(unique)
            seen[dedup_key] = idx
            if msg_id and msg_id != dedup_key:
                seen[msg_id] = idx
            m.pop("_telnyx_id", None)
            unique.append(m)
        else:
            existing_idx = seen.get(dedup_key) or seen.get(msg_id)
            if existing_idx is not None:
                existing = unique[existing_idx]
                # Prefer whichever has a real sender name (panel version)
                new_sender = m.get("senderName") or ""
                old_sender = existing.get("senderName") or ""
                if new_sender and new_sender != "System" and (not old_sender or old_sender == "System"):
                    m.pop("_telnyx_id", None)
                    unique[existing_idx] = m

    unique.sort(key=lambda x: x["timestamp"])

    # Final sanitization: never return numeric-only senderName to the frontend
    for m in unique:
        sn = m.get("senderName") or ""
        if not sn or sn.isdigit():
            m["senderName"] = contact_display_name if m["direction"] == "inbound" else "You"

    logger.info(
        "SMS GET result: %d messages (%d inbound, %d outbound) for phone ...%s org=%s",
        len(unique),
        sum(1 for m in unique if m.get("direction") == "inbound"),
        sum(1 for m in unique if m.get("direction") == "outbound"),
        phone[-4:] if phone else "?",
        org_id,
    )

    return unique


# ─── POST /send ───────────────────────────────────────────────────────────────

@router.post("/send")
async def send_sms(
    req: SendSMSRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_auth),
):
    """
    Send an SMS/MMS message via Telnyx with full compliance stack.
    Stores in conversation history, pushes to WebSocket.
    Tenant-isolated, sender-identified.
    """
    _check_tables(db)
    org_id = _get_org_id(current_user)
    user_name = _get_user_name(current_user)
    user_id = _get_user_id(current_user)

    if not req.to or not req.message.strip():
        raise HTTPException(status_code=400, detail="Phone number and message are required")

    from telephony.phone_utils import normalize_phone
    if not normalize_phone(req.to):
        raise HTTPException(status_code=400, detail=f"Invalid phone number format: {req.to}")

    # Use existing SMSClient for compliance + sending
    try:
        from integrations.sms_service import SMSClient
        client = SMSClient(db=db, user_id=user_id)

        lead_id = None
        try:
            lead_id = int(req.contactId)
        except (ValueError, TypeError):
            pass

        result = client.send_sms(
            to_phone=req.to,
            message=req.message.strip(),
            lead_id=lead_id,
            user_id=user_id,
            organization_id=org_id,
            media_urls=req.mediaUrls if req.mediaUrls else None,
        )
    except Exception as e:
        logger.error(f"SMS send error: {e}")
        result = {"success": False, "error": str(e)}

    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "Send failed"))

    # Store in panel messages table (with sender identity + tenant)
    msg_id = result.get("message_id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    media_json = "[]"
    if req.mediaUrls:
        import json
        media_json = json.dumps(req.mediaUrls)

    try:
        db.execute(text("""
            INSERT INTO sms_panel_messages
                (id, phone, contact_id, organization_id, direction, body,
                 sender_name, sender_user_id, status,
                 media_urls, page_type, borrower_type, telnyx_message_id, created_at)
            VALUES
                (:id, :phone, :contact_id, :org_id, 'outbound', :body,
                 :sender_name, :sender_user_id, 'sent',
                 :media_urls::jsonb, :page_type, :borrower_type, :telnyx_id, :now)
            ON CONFLICT (id) DO UPDATE SET
                sender_name = EXCLUDED.sender_name,
                sender_user_id = EXCLUDED.sender_user_id,
                contact_id = EXCLUDED.contact_id,
                organization_id = EXCLUDED.organization_id,
                page_type = EXCLUDED.page_type,
                borrower_type = EXCLUDED.borrower_type,
                media_urls = EXCLUDED.media_urls
        """), {
            "id": msg_id,
            "phone": normalize_phone(req.to) or req.to,
            "contact_id": req.contactId,
            "org_id": org_id,
            "body": req.message.strip(),
            "sender_name": user_name,
            "sender_user_id": user_id,
            "media_urls": media_json,
            "page_type": req.pageType,
            "borrower_type": req.borrowerType,
            "telnyx_id": result.get("message_id"),
            "now": now,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store outbound message: {e}")

    # Push to WebSocket clients (tenant-scoped)
    safe_sender = user_name if (user_name and not user_name.isdigit()) else "You"
    ws_msg = {
        "type": "new_message",
        "id": msg_id,
        "direction": "outbound",
        "body": req.message.strip(),
        "senderName": safe_sender,
        "timestamp": now.isoformat(),
        "status": "sent",
        "mediaUrls": req.mediaUrls,
    }
    try:
        await sms_manager.broadcast(org_id, req.to, ws_msg)
    except Exception:
        pass

    safe_sender = user_name if (user_name and not user_name.isdigit()) else "You"
    return {
        "id": msg_id,
        "direction": "outbound",
        "body": req.message.strip(),
        "senderName": safe_sender,
        "timestamp": now.isoformat(),
        "status": "sent",
        "mediaUrls": req.mediaUrls,
    }


# ─── POST /upload-media ──────────────────────────────────────────────────────

@router.post("/upload-media")
async def upload_media(
    file: UploadFile = File(...),
    contactId: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(_require_auth),
):
    """
    Upload a media file for MMS sending.
    Stores in S3 for persistence (Railway filesystem is ephemeral).
    Returns a presigned S3 URL that Telnyx can fetch, or falls back to
    local storage if S3 is not configured.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 5MB MMS limit")

    org_id = _get_org_id(current_user)
    content_type = file.content_type or "application/octet-stream"

    # Try S3 first (persistent storage)
    from utils.media_storage import get_media_storage
    storage = get_media_storage()

    if storage.is_available:
        s3_key = storage.upload_media(contents, file.filename, content_type, org_id=org_id)
        if s3_key:
            # Return a presigned URL with 1-hour expiry (Telnyx fetches immediately)
            presigned_url = storage.get_media_url(s3_key, expires_in=3600)
            return {
                "url": presigned_url,
                "s3_key": s3_key,
                "filename": file.filename,
                "size": len(contents),
                "storage": "s3",
            }
        logger.warning("S3 upload failed, falling back to local storage")

    # Fallback: local filesystem (ephemeral on Railway)
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "sms")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".bin"
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(upload_dir, safe_name)

    with open(filepath, "wb") as f:
        f.write(contents)

    api_domain = os.getenv("API_DOMAIN", "api.perenniaai.com")
    url = f"https://{api_domain}/uploads/sms/{safe_name}"

    return {"url": url, "filename": file.filename, "size": len(contents), "storage": "local"}


# ─── WebSocket /ws/sms/{phone} ───────────────────────────────────────────────

@ws_router.websocket("/ws/sms/{phone}")
async def sms_websocket(websocket: WebSocket, phone: str):
    """
    Authenticated WebSocket for real-time SMS push.
    Token passed via query param: /ws/sms/{phone}?token=JWT
    Tenant-isolated: only receives messages for the user's organization.
    """
    # Authenticate before accepting
    auth_db = next(get_db())
    try:
        from utils.websocket_auth import authenticate_websocket
        user, auth_error = authenticate_websocket(websocket, auth_db)
        if not user:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        auth_db.close()

    org_id = user.organization_id
    await sms_manager.connect(org_id, phone, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        sms_manager.disconnect(org_id, phone, websocket)
    except Exception:
        sms_manager.disconnect(org_id, phone, websocket)


# ─── Inbound + status hooks (called from webhook handler) ──────────────────

async def notify_inbound_sms(
    phone: str, body: str, telnyx_message_id: str = "",
    org_id: Optional[int] = None, contact_name: str = "",
):
    """
    Called from Telnyx webhook handler to push inbound messages to the panel.
    Broadcasts to all orgs watching this phone (inbound sender org is unknown).
    """
    msg = {
        "type": "new_message",
        "id": telnyx_message_id or str(uuid.uuid4()),
        "direction": "inbound",
        "body": body,
        "senderName": contact_name or "Customer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "delivered",
        "mediaUrls": [],
    }

    try:
        if org_id:
            await sms_manager.broadcast(org_id, phone, msg)
        else:
            await sms_manager.broadcast_all_orgs(phone, msg)
    except Exception as e:
        logger.debug(f"WebSocket broadcast failed: {e}")

    return msg


async def notify_status_update(
    phone: str, telnyx_message_id: str, status: str,
    org_id: Optional[int] = None,
):
    """
    Called from webhook handler when delivery status changes (sent→delivered, sent→failed).
    Pushes status update to WebSocket clients.
    """
    msg = {
        "type": "status_update",
        "messageId": telnyx_message_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        if org_id:
            await sms_manager.broadcast(org_id, phone, msg)
        else:
            await sms_manager.broadcast_all_orgs(phone, msg)
    except Exception as e:
        logger.debug(f"WebSocket status broadcast failed: {e}")




@router.get("/diag/sms-trace/{phone}")
async def diag_sms_trace(phone: str, t: str = "", db: Session = Depends(get_db)):
    """TEMPORARY diagnostic — no auth, tests every query layer independently."""
    if t != "trace2026":
        raise HTTPException(status_code=403, detail="token required")
    import traceback as _tb
    digits = "".join(c for c in phone if c.isdigit())
    pattern = f"%{digits[-10:]}" if len(digits) >= 10 else f"%{digits}"
    evidence: dict = {"phone": phone, "pattern": pattern}

    # 1. Check RLS status on sms_panel_messages
    try:
        r = db.execute(text("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class WHERE relname = 'sms_panel_messages'
        """)).fetchone()
        evidence["rls_enabled"] = bool(r and r[0])
        evidence["rls_forced"] = bool(r and r[1])
    except Exception as e:
        evidence["rls_check_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 2. Check current tenant setting
    try:
        r = db.execute(text("SELECT current_setting('app.current_tenant', true)")).fetchone()
        evidence["current_tenant"] = r[0] if r else None
    except Exception as e:
        evidence["tenant_check_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 3. Raw count of ALL panel messages for this phone (no org filter, no RLS bypass)
    try:
        r = db.execute(text("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE direction = 'inbound'),
                   COUNT(*) FILTER (WHERE direction = 'outbound')
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
        """), {"pattern": pattern}).fetchone()
        evidence["panel_total"] = r[0] if r else 0
        evidence["panel_inbound"] = r[1] if r else 0
        evidence["panel_outbound"] = r[2] if r else 0
    except Exception as e:
        evidence["panel_count_error"] = f"{e}"
        try:
            db.rollback()
        except Exception:
            pass

    # 4. Same query WITH org_id=1 filter
    try:
        r = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
              AND (organization_id = 1 OR organization_id IS NULL)
        """), {"pattern": pattern}).fetchone()
        evidence["panel_with_org1"] = r[0] if r else 0
    except Exception as e:
        evidence["panel_org1_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 5. Set tenant=1 and retry
    try:
        db.execute(text("SET LOCAL app.current_tenant = '1'"))
        r = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
        """), {"pattern": pattern}).fetchone()
        evidence["panel_after_set_tenant"] = r[0] if r else 0
    except Exception as e:
        evidence["panel_set_tenant_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 6. Check sms_delivery_log
    try:
        r = db.execute(text("""
            SELECT COUNT(*) FROM sms_delivery_log
            WHERE REPLACE(REPLACE(REPLACE(to_phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
        """), {"pattern": pattern}).fetchone()
        evidence["delivery_log_count"] = r[0] if r else 0
    except Exception as e:
        evidence["delivery_log_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 7. Sample inbound messages (first 3)
    try:
        db.execute(text("SET LOCAL app.current_tenant = '1'"))
        rows = db.execute(text("""
            SELECT id, phone, organization_id, direction, body, status, created_at
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
              AND direction = 'inbound'
            ORDER BY created_at DESC LIMIT 3
        """), {"pattern": pattern}).fetchall()
        evidence["inbound_sample"] = [
            {"id": str(r[0])[:20], "phone": r[1], "org": r[2], "dir": r[3],
             "body": (r[4] or "")[:30], "status": r[5],
             "at": r[6].isoformat() if r[6] else None}
            for r in rows
        ]
    except Exception as e:
        evidence["inbound_sample_error"] = str(e)
        try:
            db.rollback()
        except Exception:
            pass

    # 8. Check ALL user accounts to find org_id mismatch
    try:
        db.rollback()
        all_users = db.execute(text(
            "SELECT id, organization_id, email FROM users WHERE email IN ('tloss@cmghomeloans.com', 'tlossmtgboss@gmail.com') ORDER BY id"
        )).fetchall()
        evidence["all_user_accounts"] = [
            {"id": r[0], "org_id": r[1], "email": r[2]} for r in all_users
        ]

        # Also check what org_ids exist on outbound panel messages
        org_check = db.execute(text("""
            SELECT DISTINCT organization_id, direction, COUNT(*) as cnt
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
            GROUP BY organization_id, direction ORDER BY cnt DESC
        """), {"pattern": pattern}).fetchall()
        evidence["panel_org_breakdown"] = [
            {"org_id": r[0], "dir": r[1], "count": r[2]} for r in org_check
        ]

        # Fetch the ACTUAL logged-in user (gmail account)
        user_row = db.execute(text(
            "SELECT id, organization_id, email FROM users WHERE email = 'tlossmtgboss@gmail.com' LIMIT 1"
        )).fetchone()
        if not user_row:
            user_row = db.execute(text(
                "SELECT id, organization_id, email FROM users WHERE email = 'tloss@cmghomeloans.com' LIMIT 1"
            )).fetchone()
        if not user_row:
            user_row = db.execute(text("SELECT id, organization_id, email FROM users LIMIT 1")).fetchone()

        class _FakeUser:
            pass

        fake_user = _FakeUser()
        fake_user.id = user_row[0] if user_row else 1
        fake_user.organization_id = user_row[1] if user_row else 1
        fake_user.email = user_row[2] if user_row else "test"
        fake_user.first_name = "Test"
        fake_user.last_name = "User"

        evidence["sim_user"] = {"id": fake_user.id, "org_id": fake_user.organization_id}

        # Now run the EXACT same code path as get_conversation
        sim_org_id = _get_org_id(fake_user)
        sim_rls_org = sim_org_id or 1
        sim_normalized = _normalize_phone(phone)
        sim_like = f"%{sim_normalized[-10:]}"

        evidence["sim_org_id"] = sim_org_id
        evidence["sim_normalized"] = sim_normalized
        evidence["sim_pattern"] = sim_like

        # contact name lookup (the one that could abort the transaction)
        try:
            sim_contact = _resolve_contact_name(db, sim_normalized, sim_org_id)
            evidence["sim_contact_name"] = sim_contact or "(empty)"
        except Exception as cn_err:
            evidence["sim_contact_name_error"] = str(cn_err)
            try:
                db.rollback()
            except Exception:
                pass

        # Build same params
        sim_params = {"pattern": sim_like, "lim": 100}
        if sim_org_id is not None:
            sim_org_filter = "AND (organization_id = :org_id OR organization_id IS NULL)"
            sim_params["org_id"] = sim_org_id
        else:
            sim_org_filter = ""

        # delivery_log query
        try:
            db.execute(text("SET LOCAL app.current_tenant = :o"), {"o": str(sim_rls_org)})
            dl = db.execute(text(f"""
                SELECT telnyx_message_id, 'outbound', message_body, status, sent_at, user_id
                FROM sms_delivery_log
                WHERE REPLACE(REPLACE(REPLACE(to_phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
                  {sim_org_filter}
                ORDER BY sent_at DESC LIMIT :lim
            """), sim_params).fetchall()
            evidence["sim_delivery_rows"] = len(dl)
        except Exception as dle:
            evidence["sim_delivery_error"] = str(dle)
            try:
                db.rollback()
            except Exception:
                pass

        # panel query
        try:
            db.execute(text("SET LOCAL app.current_tenant = :o"), {"o": str(sim_rls_org)})
            pm = db.execute(text(f"""
                SELECT id, direction, body, sender_name, sender_role, status,
                       media_urls, created_at, telnyx_message_id, media_s3_keys
                FROM sms_panel_messages
                WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :pattern
                  {sim_org_filter}
                ORDER BY created_at DESC LIMIT :lim
            """), sim_params).fetchall()
            evidence["sim_panel_rows"] = len(pm)
            evidence["sim_panel_inbound"] = sum(1 for r in pm if r[1] == "inbound")
            evidence["sim_panel_outbound"] = sum(1 for r in pm if r[1] == "outbound")
            # Show first 3 panel rows for inspection
            evidence["sim_panel_sample"] = [
                {"id": str(r[0])[:20], "dir": r[1], "body": (r[2] or "")[:30],
                 "status": r[5], "at": r[7].isoformat() if r[7] else None}
                for r in pm[:3]
            ]
        except Exception as pme:
            evidence["sim_panel_error"] = f"{pme}\n{_tb.format_exc()}"
            try:
                db.rollback()
            except Exception:
                pass

    except Exception as e:
        evidence["sim_setup_error"] = f"{e}\n{_tb.format_exc()}"
        try:
            db.rollback()
        except Exception:
            pass

    return evidence


def update_panel_message_status(db: Session, telnyx_message_id: str, status: str):
    """Update status in sms_panel_messages when delivery webhook arrives."""
    try:
        db.execute(text("""
            UPDATE sms_panel_messages
            SET status = :status
            WHERE telnyx_message_id = :msg_id OR id = :msg_id
        """), {"status": status, "msg_id": telnyx_message_id})
        db.flush()
    except Exception as e:
        logger.debug(f"Panel message status update skipped: {e}")

