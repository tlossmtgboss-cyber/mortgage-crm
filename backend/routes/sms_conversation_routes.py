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
from typing import Optional

from fastapi import (
    APIRouter, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, UploadFile, File, Form,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sms", tags=["SMS Conversations"])
ws_router = APIRouter()

_security = HTTPBearer(auto_error=False)


# ─── Auth helper (lazy import to avoid circular deps) ───────────────────────

async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    """Authenticate the request and return the current user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(
        token=credentials.credentials, request=None, db=db,
    )
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
    contactId: str
    to: str
    message: str
    mediaUrls: list[str] = []
    pageType: str = "client"
    borrowerType: str = "primary"


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
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Table creation skipped (may already exist): {e}")


_tables_checked = False


def _check_tables(db: Session):
    global _tables_checked
    if not _tables_checked:
        _ensure_tables(db)
        _tables_checked = True


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
    normalized = _normalize_phone(phone)
    like_pattern = f"%{normalized[-10:]}"  # match last 10 digits

    # Build optional cursor filter
    before_filter = ""
    params: dict = {"pattern": like_pattern, "lim": limit, "org_id": org_id}
    if before:
        before_filter = "AND sent_at < :before"
        params["before"] = before

    messages = []

    # 1. Outbound from sms_delivery_log (existing Telnyx tracking table)
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
            {before_filter}
            ORDER BY sent_at DESC
            LIMIT :lim
        """), params).fetchall()

        for r in rows:
            # Look up sender name from user_id if available
            sender_name = "System"
            sender_user_id = r[5]
            if sender_user_id:
                try:
                    user_row = db.execute(text(
                        "SELECT first_name, last_name FROM users WHERE id = :uid"
                    ), {"uid": sender_user_id}).fetchone()
                    if user_row:
                        name = f"{user_row[0] or ''} {user_row[1] or ''}".strip()
                        sender_name = name or "System"
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
        logger.debug(f"sms_delivery_log query skipped: {e}")

    # 2. Messages from sms_panel_messages (two-way table, tenant-isolated)
    before_filter_panel = ""
    if before:
        before_filter_panel = "AND created_at < :before"

    try:
        rows = db.execute(text(f"""
            SELECT id, direction, body, sender_name, sender_role, status,
                   media_urls, created_at, telnyx_message_id, media_s3_keys
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '')
                  LIKE :pattern
              AND (organization_id = :org_id OR organization_id IS NULL)
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

            messages.append({
                "id": r[0],
                "direction": r[1],
                "body": r[2] or "",
                "senderName": r[3] or ("System" if r[1] == "outbound" else "Customer"),
                "senderRole": r[4],
                "timestamp": r[7].isoformat() if r[7] else datetime.now(timezone.utc).isoformat(),
                "status": r[5] or "delivered",
                "mediaUrls": resolved_urls,
                "_telnyx_id": r[8],  # for dedup
            })
    except Exception as e:
        logger.debug(f"sms_panel_messages query skipped: {e}")

    # Deduplicate: panel outbound messages share telnyx_message_id with delivery_log
    seen_ids = set()
    unique = []
    for m in messages:
        # Use telnyx_message_id for dedup when available
        dedup_key = m.get("_telnyx_id") or m["id"]
        if dedup_key not in seen_ids:
            seen_ids.add(dedup_key)
            # Also add the message id itself to avoid showing both entries
            seen_ids.add(m["id"])
            m.pop("_telnyx_id", None)
            unique.append(m)
        else:
            # If duplicate, prefer the panel version (has sender name)
            pass

    unique.sort(key=lambda x: x["timestamp"])

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

    # Use existing SMSClient for compliance + sending
    try:
        from integrations.sms_service import SMSClient
        client = SMSClient(db=db, user_id=user_id)

        lead_id = None
        try:
            lead_id = int(req.contactId)
        except (ValueError, TypeError):
            pass

        result = await client.send_sms(
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
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": msg_id,
            "phone": req.to,
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
    ws_msg = {
        "type": "new_message",
        "id": msg_id,
        "direction": "outbound",
        "body": req.message.strip(),
        "senderName": user_name,
        "timestamp": now.isoformat(),
        "status": "sent",
        "mediaUrls": req.mediaUrls,
    }
    try:
        await sms_manager.broadcast(org_id, req.to, ws_msg)
    except Exception:
        pass

    return {
        "id": msg_id,
        "direction": "outbound",
        "body": req.message.strip(),
        "senderName": user_name,
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
    org_id: Optional[int] = None,
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
        "senderName": "Customer",
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
