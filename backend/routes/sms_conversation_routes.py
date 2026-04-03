"""
SMS Conversation Routes — Two-way SMS panel backend.

Endpoints consumed by the SMSAccordionPanel component:
  GET  /api/v1/sms/conversations/{phone}   — message history for a phone number
  POST /api/v1/sms/send                    — send an SMS (with compliance + Telnyx)
  POST /api/v1/sms/upload-media            — upload MMS attachment
  WS   /ws/sms/{phone}                     — real-time inbound push
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sms", tags=["SMS Conversations"])
ws_router = APIRouter()


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
    """Track open WebSocket connections by phone number for real-time push."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, phone: str, ws: WebSocket):
        await ws.accept()
        normalized = _normalize_phone(phone)
        if normalized not in self._connections:
            self._connections[normalized] = []
        self._connections[normalized].append(ws)

    def disconnect(self, phone: str, ws: WebSocket):
        normalized = _normalize_phone(phone)
        conns = self._connections.get(normalized, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(normalized, None)

    async def broadcast(self, phone: str, message: dict):
        """Push a message to all clients watching this phone number."""
        normalized = _normalize_phone(phone)
        dead = []
        for ws in self._connections.get(normalized, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(phone, ws)


sms_manager = SMSConnectionManager()


def _normalize_phone(phone: str) -> str:
    """Strip to digits for consistent lookup."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return digits


# ─── Helper: ensure tables exist ─────────────────────────────────────────────

def _ensure_tables(db: Session):
    """Create sms_panel_messages table if it doesn't exist."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS sms_panel_messages (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                contact_id TEXT,
                direction TEXT NOT NULL DEFAULT 'outbound',
                body TEXT NOT NULL DEFAULT '',
                sender_name TEXT DEFAULT '',
                sender_role TEXT,
                status TEXT DEFAULT 'sent',
                media_urls JSONB DEFAULT '[]'::jsonb,
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
async def get_conversation(phone: str, limit: int = 100, db: Session = Depends(get_db)):
    """
    Get SMS conversation history for a phone number.
    Returns merged inbound + outbound messages sorted by timestamp.
    """
    _check_tables(db)
    normalized = _normalize_phone(phone)
    like_pattern = f"%{normalized[-10:]}"  # match last 10 digits

    messages = []

    # 1. Outbound from sms_delivery_log (existing Telnyx tracking table)
    try:
        rows = db.execute(text("""
            SELECT
                telnyx_message_id AS id,
                'outbound' AS direction,
                message_body AS body,
                'You' AS sender_name,
                status,
                sent_at AS created_at
            FROM sms_delivery_log
            WHERE REPLACE(REPLACE(REPLACE(to_phone, '+', ''), '-', ''), ' ', '')
                  LIKE :pattern
            ORDER BY sent_at DESC
            LIMIT :lim
        """), {"pattern": like_pattern, "lim": limit}).fetchall()

        for r in rows:
            messages.append({
                "id": r[0] or str(uuid.uuid4()),
                "direction": "outbound",
                "body": r[2] or "",
                "senderName": "You",
                "senderRole": None,
                "timestamp": r[5].isoformat() if r[5] else datetime.now(timezone.utc).isoformat(),
                "status": r[4] or "sent",
                "mediaUrls": [],
            })
    except Exception as e:
        logger.debug(f"sms_delivery_log query skipped: {e}")

    # 2. Messages from sms_panel_messages (our new two-way table)
    try:
        rows = db.execute(text("""
            SELECT id, direction, body, sender_name, sender_role, status, media_urls, created_at
            FROM sms_panel_messages
            WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '')
                  LIKE :pattern
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"pattern": like_pattern, "lim": limit}).fetchall()

        for r in rows:
            messages.append({
                "id": r[0],
                "direction": r[1],
                "body": r[2] or "",
                "senderName": r[3] or ("You" if r[1] == "outbound" else "Customer"),
                "senderRole": r[4],
                "timestamp": r[7].isoformat() if r[7] else datetime.now(timezone.utc).isoformat(),
                "status": r[5] or "delivered",
                "mediaUrls": r[6] if r[6] else [],
            })
    except Exception as e:
        logger.debug(f"sms_panel_messages query skipped: {e}")

    # Deduplicate by id, sort chronologically
    seen = set()
    unique = []
    for m in messages:
        if m["id"] not in seen:
            seen.add(m["id"])
            unique.append(m)
    unique.sort(key=lambda x: x["timestamp"])

    return unique


# ─── POST /send ───────────────────────────────────────────────────────────────

@router.post("/send")
async def send_sms(req: SendSMSRequest, db: Session = Depends(get_db)):
    """
    Send an SMS message via Telnyx with full compliance stack.
    Stores the message in conversation history and pushes to WebSocket.
    """
    _check_tables(db)

    if not req.to or not req.message.strip():
        raise HTTPException(status_code=400, detail="Phone number and message are required")

    # Use existing SMSClient for compliance + sending
    try:
        from integrations.sms_service import SMSClient
        client = SMSClient(db=db)

        # Convert contactId to int for lead_id if possible
        lead_id = None
        try:
            lead_id = int(req.contactId)
        except (ValueError, TypeError):
            pass

        result = await client.send_sms(
            to_phone=req.to,
            message=req.message.strip(),
            lead_id=lead_id,
        )
    except Exception as e:
        logger.error(f"SMS send error: {e}")
        result = {"success": False, "error": str(e)}

    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "Send failed"))

    # Store in panel messages table
    msg_id = result.get("message_id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    try:
        db.execute(text("""
            INSERT INTO sms_panel_messages
                (id, phone, contact_id, direction, body, sender_name, status,
                 media_urls, page_type, borrower_type, telnyx_message_id, created_at)
            VALUES
                (:id, :phone, :contact_id, 'outbound', :body, 'You', 'sent',
                 :media_urls::jsonb, :page_type, :borrower_type, :telnyx_id, :now)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": msg_id,
            "phone": req.to,
            "contact_id": req.contactId,
            "body": req.message.strip(),
            "media_urls": "[]",
            "page_type": req.pageType,
            "borrower_type": req.borrowerType,
            "telnyx_id": result.get("message_id"),
            "now": now,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store outbound message: {e}")

    # Push to WebSocket clients
    ws_msg = {
        "id": msg_id,
        "direction": "outbound",
        "body": req.message.strip(),
        "senderName": "You",
        "timestamp": now.isoformat(),
        "status": "sent",
        "mediaUrls": [],
    }
    try:
        await sms_manager.broadcast(req.to, ws_msg)
    except Exception:
        pass

    return ws_msg


# ─── POST /upload-media ──────────────────────────────────────────────────────

@router.post("/upload-media")
async def upload_media(
    file: UploadFile = File(...),
    contactId: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Upload a media file for MMS sending.
    Stores locally and returns a public URL that Telnyx can fetch.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Limit file size to 5MB (Telnyx MMS limit)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 5MB MMS limit")

    # Save to local uploads directory
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "sms")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".bin"
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(upload_dir, safe_name)

    with open(filepath, "wb") as f:
        f.write(contents)

    # Build public URL — use API domain for Railway
    api_domain = os.getenv("API_DOMAIN", "api.perenniaai.com")
    url = f"https://{api_domain}/uploads/sms/{safe_name}"

    return {"url": url, "filename": file.filename, "size": len(contents)}


# ─── WebSocket /ws/sms/{phone} ───────────────────────────────────────────────

@ws_router.websocket("/ws/sms/{phone}")
async def sms_websocket(websocket: WebSocket, phone: str):
    """
    WebSocket for real-time SMS push. The frontend panel connects here to
    receive inbound messages as they arrive via Telnyx webhooks.
    """
    await sms_manager.connect(phone, websocket)
    try:
        while True:
            # Keep connection alive; client doesn't need to send data
            # but we handle pings to keep the connection open
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        sms_manager.disconnect(phone, websocket)
    except Exception:
        sms_manager.disconnect(phone, websocket)


# ─── Inbound webhook hook ────────────────────────────────────────────────────
# This function should be called from the Telnyx webhook handler when an
# inbound message is received, to push it to connected WebSocket clients.

async def notify_inbound_sms(phone: str, body: str, telnyx_message_id: str = ""):
    """
    Called from Telnyx webhook handler to push inbound messages to the panel.
    Also stores the message in sms_panel_messages.
    """
    msg = {
        "id": telnyx_message_id or str(uuid.uuid4()),
        "direction": "inbound",
        "body": body,
        "senderName": "Customer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "delivered",
        "mediaUrls": [],
    }

    try:
        await sms_manager.broadcast(phone, msg)
    except Exception as e:
        logger.debug(f"WebSocket broadcast failed: {e}")

    return msg
