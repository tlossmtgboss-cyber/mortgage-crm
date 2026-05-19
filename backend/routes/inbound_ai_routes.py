"""
Inbound AI Call Answering Routes
================================
When an inbound call arrives on an LO's number:
  1. Telnyx webhook fires call.initiated
  2. Look up LO by called number (user_twilio_config + fallback)
  3. Check LO availability (lo_availability table)
  4. If LO available -> answer, ring LO cell for configurable timeout
  5. If LO unavailable or ring timeout -> Vapi AI (Aria) takes over
  6. Vapi calls function tools: schedule_callback, take_message
  7. End-of-call-report logs transcript + summary to vapi_calls + activities

Prefix: /api/v1/telephony
"""

import os
import json
import hmac
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from db import get_db
from routes.auth_deps import current_user_flexible_dep
from middleware.webhook_verification import require_vapi_webhook
from services.voice_context_builder import build_inbound_context, build_transfer_whisper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telephony", tags=["Inbound AI"])

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_API_BASE = "https://api.vapi.ai"
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_API_BASE = "https://api.telnyx.com/v2"
TELNYX_CONNECTION_ID = os.getenv("TELNYX_CONNECTION_ID", "")

API_BASE_URL = (
    os.getenv("API_URL")
    or os.getenv("PRODUCTION_DOMAIN")
    or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    or "https://api.perenniaai.com"
)
if API_BASE_URL and not API_BASE_URL.startswith("http"):
    API_BASE_URL = f"https://{API_BASE_URL}"

DEFAULT_LO_RING_TIMEOUT = 20  # seconds before AI picks up
DEFAULT_GREETING = (
    "Hi, this is Aria from {company}. {lo_name} is unavailable right now, "
    "but I can help you. What can I do for you today?"
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class InboundConfigUpdate(BaseModel):
    ai_answering_enabled: Optional[bool] = None
    greeting_text: Optional[str] = Field(None, max_length=500)
    lo_ring_timeout: Optional[int] = Field(None, ge=5, le=60)
    vapi_assistant_id: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)


class InboundConfigResponse(BaseModel):
    ai_answering_enabled: bool = True
    greeting_text: Optional[str] = None
    lo_ring_timeout: int = DEFAULT_LO_RING_TIMEOUT
    vapi_assistant_id: Optional[str] = None
    company_name: Optional[str] = None
    organization_id: Optional[int] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """Normalize phone number to last 10 digits."""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))[-10:]


def _get_org_id(current_user) -> Optional[int]:
    """Extract organization_id from user (dict or ORM object)."""
    if isinstance(current_user, dict):
        return current_user.get("organization_id")
    return getattr(current_user, "organization_id", None)


def _get_user_id(current_user) -> Optional[int]:
    """Extract user id."""
    if isinstance(current_user, dict):
        return current_user.get("id")
    return getattr(current_user, "id", None)


# ---------------------------------------------------------------------------
# HTTP helpers for Telnyx and Vapi
# ---------------------------------------------------------------------------

async def _telnyx_post(path: str, payload: dict, timeout: int = 15) -> dict:
    """POST to Telnyx Call Control API."""
    if not TELNYX_API_KEY:
        logger.error("TELNYX_API_KEY not configured")
        return {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{TELNYX_API_BASE}{path}",
            json=payload,
            headers={
                "Authorization": f"Bearer {TELNYX_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            logger.error("Telnyx API error %s: %s", resp.status_code, resp.text[:500])
        return resp.json() if resp.content else {}


async def _vapi_post(path: str, payload: dict, timeout: int = 20) -> dict:
    """POST to Vapi API."""
    if not VAPI_API_KEY:
        logger.error("VAPI_API_KEY not configured")
        return {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{VAPI_API_BASE}{path}",
            json=payload,
            headers={
                "Authorization": f"Bearer {VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            logger.error("Vapi API error %s: %s", resp.status_code, resp.text[:500])
            return {}
        return resp.json() if resp.content else {}


# ---------------------------------------------------------------------------
# LO Lookup
# ---------------------------------------------------------------------------

def _find_lo_by_phone(db: Session, to_number: str) -> Optional[Dict[str, Any]]:
    """
    Find the LO whose Telnyx/business number matches the called number.

    Search order:
      1. user_twilio_config.telnyx_phone_number (per-user provisioned)
      2. Global TELNYX_PHONE_NUMBER env var (shared number)
    """
    phone_clean = _normalize_phone(to_number)
    if not phone_clean or len(phone_clean) < 10:
        return None

    # 1. Per-user phone mapping in user_twilio_config
    try:
        row = db.execute(text("""
            SELECT utc.user_id, u.first_name, u.last_name, u.email,
                   u.cell_phone, u.phone, u.organization_id,
                   o.name AS org_name
            FROM user_twilio_config utc
            JOIN users u ON u.id = utc.user_id
            LEFT JOIN organizations o ON o.id = u.organization_id
            WHERE utc.telnyx_phone_number LIKE :phone_pattern
            LIMIT 1
        """), {"phone_pattern": f"%{phone_clean}"}).fetchone()

        if row:
            return {
                "user_id": row.user_id,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "full_name": f"{row.first_name or ''} {row.last_name or ''}".strip() or "your loan officer",
                "email": row.email,
                "cell_phone": row.cell_phone or row.phone,
                "organization_id": row.organization_id,
                "org_name": row.org_name or "our team",
            }
    except Exception as e:
        logger.warning("user_twilio_config lookup failed: %s", e)

    # 2. Fallback: global TELNYX_PHONE_NUMBER
    global_phone = os.getenv("TELNYX_PHONE_NUMBER", "")
    global_clean = _normalize_phone(global_phone)
    if global_clean and global_clean == phone_clean:
        try:
            row = db.execute(text("""
                SELECT u.id AS user_id, u.first_name, u.last_name, u.email,
                       u.cell_phone, u.phone, u.organization_id,
                       o.name AS org_name
                FROM users u
                LEFT JOIN organizations o ON o.id = u.organization_id
                WHERE u.role IN ('admin', 'loan_officer', 'owner')
                  AND u.is_active = TRUE
                ORDER BY u.id ASC
                LIMIT 1
            """)).fetchone()
            if row:
                return {
                    "user_id": row.user_id,
                    "first_name": row.first_name,
                    "last_name": row.last_name,
                    "full_name": f"{row.first_name or ''} {row.last_name or ''}".strip() or "your loan officer",
                    "email": row.email,
                    "cell_phone": row.cell_phone or row.phone,
                    "organization_id": row.organization_id,
                    "org_name": row.org_name or "our team",
                }
        except Exception as e:
            logger.warning("Global phone LO lookup failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# LO Availability
# ---------------------------------------------------------------------------

def _is_lo_available(db: Session, user_id: int) -> bool:
    """
    Check if LO is available to take calls.

    Uses lo_availability table. Returns True if no record exists (LO has not
    configured presence yet).
    """
    try:
        row = db.execute(text("""
            SELECT status, last_heartbeat_at, active_transfer_count,
                   max_concurrent_transfers
            FROM lo_availability
            WHERE user_id = :uid
        """), {"uid": user_id}).fetchone()

        if not row:
            return True  # No availability record = assume available

        if row.status != "available":
            return False

        # Heartbeat freshness: stale if > 5 min
        if row.last_heartbeat_at:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            hb = row.last_heartbeat_at
            if hb.tzinfo is None:
                hb = hb.replace(tzinfo=timezone.utc)
            if hb < cutoff:
                return False

        # Transfer capacity
        max_transfers = row.max_concurrent_transfers or 1
        active = row.active_transfer_count or 0
        if active >= max_transfers:
            return False

        return True
    except Exception as e:
        logger.debug("lo_availability check failed (assuming available): %s", e)
        return True


# ---------------------------------------------------------------------------
# Inbound Config Table + Helpers
# ---------------------------------------------------------------------------

def _ensure_inbound_config_table(db: Session):
    """Create vapi_inbound_configs table if not present."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS vapi_inbound_configs (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE,
                ai_answering_enabled BOOLEAN DEFAULT TRUE,
                greeting_text TEXT,
                lo_ring_timeout INTEGER DEFAULT 20,
                vapi_assistant_id VARCHAR(255),
                company_name VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_vapi_inbound_cfg_org
            ON vapi_inbound_configs(organization_id)
        """))
        # Add company_name column if missing (table may have been created earlier)
        db.execute(text("""
            ALTER TABLE vapi_inbound_configs
            ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)
        """))
        db.commit()
    except Exception as e:
        logger.debug("vapi_inbound_configs DDL check (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


def _get_inbound_config(db: Session, org_id: int) -> Dict[str, Any]:
    """Get inbound config for an org, with sensible defaults."""
    try:
        row = db.execute(text("""
            SELECT ai_answering_enabled, greeting_text, lo_ring_timeout,
                   vapi_assistant_id, company_name, updated_at
            FROM vapi_inbound_configs
            WHERE organization_id = :org_id
        """), {"org_id": org_id}).fetchone()
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        row = None

    if row:
        return {
            "ai_answering_enabled": row.ai_answering_enabled if row.ai_answering_enabled is not None else True,
            "greeting_text": row.greeting_text,
            "lo_ring_timeout": row.lo_ring_timeout or DEFAULT_LO_RING_TIMEOUT,
            "vapi_assistant_id": row.vapi_assistant_id,
            "company_name": row.company_name,
            "organization_id": org_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    return {
        "ai_answering_enabled": True,
        "greeting_text": None,
        "lo_ring_timeout": DEFAULT_LO_RING_TIMEOUT,
        "vapi_assistant_id": None,
        "company_name": None,
        "organization_id": org_id,
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# Vapi Assistant Management
# ---------------------------------------------------------------------------

async def _get_or_create_vapi_assistant(
    db: Session,
    org_id: int,
    lo_name: str,
    company_name: str,
    greeting_override: Optional[str] = None,
) -> Optional[str]:
    """
    Get existing Vapi inbound assistant for the org, or create one.

    Returns the vapi_assistant_id string, or None on failure.
    """
    config = _get_inbound_config(db, org_id)
    if config.get("vapi_assistant_id"):
        return config["vapi_assistant_id"]

    company = company_name or "our team"
    lo = lo_name or "your loan officer"

    first_message = greeting_override or DEFAULT_GREETING.format(
        company=company, lo_name=lo,
    )

    system_prompt = (
        f"You are Aria, an AI assistant for {company}. "
        f"You're answering on behalf of {lo}, a mortgage loan officer.\n\n"
        "Your role:\n"
        "- Greet callers warmly and professionally\n"
        "- Answer basic mortgage questions (general rates, loan types, process overview)\n"
        f"- Offer to schedule a callback with {lo}\n"
        "- Take messages if the caller prefers\n\n"
        "Important rules:\n"
        "- Never provide specific rate quotes or pricing commitments\n"
        "- Never provide legal or tax advice\n"
        f"- Always offer to connect them with {lo} for specific questions\n"
        "- Be concise and conversational -- this is a phone call\n"
        f"- If asked about loan status, take their name and say {lo} will follow up\n"
        "- Always confirm the caller's name and phone number before ending the call\n\n"
        "You have two tools:\n"
        f"1. schedule_callback - Schedule a callback from {lo}\n"
        f"2. take_message - Record a message for {lo}\n"
        "Use these when the caller wants to leave a message or schedule a time to talk."
    )

    webhook_url = f"{API_BASE_URL}/api/v1/telephony/vapi-inbound-webhook"

    assistant_payload = {
        "name": f"Aria Inbound - {company}",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": system_prompt}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "schedule_callback",
                        "description": "Schedule a callback from the loan officer. Use when caller wants to be called back.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "caller_name": {
                                    "type": "string",
                                    "description": "Caller's full name",
                                },
                                "caller_phone": {
                                    "type": "string",
                                    "description": "Callback phone number",
                                },
                                "preferred_time": {
                                    "type": "string",
                                    "description": "When they'd like the callback (e.g. 'tomorrow morning')",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Brief reason for the call",
                                },
                            },
                            "required": ["caller_name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "take_message",
                        "description": "Take a message for the loan officer. Use when caller wants to leave a message.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "caller_name": {
                                    "type": "string",
                                    "description": "Caller's name",
                                },
                                "caller_phone": {
                                    "type": "string",
                                    "description": "Caller's phone number",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "The message to leave",
                                },
                            },
                            "required": ["caller_name", "message"],
                        },
                    },
                },
            ],
        },
        "voice": {
            "provider": "deepgram",
            "voiceId": "asteria",
        },
        "firstMessage": first_message,
        "endCallMessage": (
            f"Thank you for calling {company}. "
            f"{lo} will be in touch. Have a great day!"
        ),
        "serverUrl": webhook_url,
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 300,
        "voicemailDetection": {
            "provider": "vapi",
            "beepMaxAwaitSeconds": 25,
        },
    }

    # Include webhook secret if configured
    if VAPI_WEBHOOK_SECRET:
        assistant_payload["serverUrlSecret"] = VAPI_WEBHOOK_SECRET

    result = await _vapi_post("/assistant", assistant_payload)
    assistant_id = result.get("id")

    if not assistant_id:
        logger.error("Vapi assistant creation returned no ID: %s", result)
        return None

    # Persist the assistant ID
    try:
        existing = db.execute(text(
            "SELECT id FROM vapi_inbound_configs WHERE organization_id = :org_id"
        ), {"org_id": org_id}).fetchone()

        now = datetime.now(timezone.utc)
        if existing:
            db.execute(text("""
                UPDATE vapi_inbound_configs
                SET vapi_assistant_id = :aid, updated_at = :now
                WHERE organization_id = :org_id
            """), {"aid": assistant_id, "now": now, "org_id": org_id})
        else:
            db.execute(text("""
                INSERT INTO vapi_inbound_configs
                    (organization_id, vapi_assistant_id, ai_answering_enabled,
                     lo_ring_timeout, company_name, created_at, updated_at)
                VALUES (:org_id, :aid, TRUE, :timeout, :company, :now, :now)
            """), {
                "org_id": org_id, "aid": assistant_id,
                "timeout": DEFAULT_LO_RING_TIMEOUT,
                "company": company, "now": now,
            })
        db.commit()
    except Exception as e:
        logger.warning("Could not persist Vapi assistant ID: %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass

    # Also record in vapi_assistants table for unified tracking
    try:
        db.execute(text("""
            INSERT INTO vapi_assistants (
                organization_id, vapi_assistant_id, name, description,
                voice_id, first_message, system_prompt, is_active, created_at
            ) VALUES (
                :org_id, :aid, :name, :desc,
                'deepgram/asteria', :first_msg, :sys_prompt, TRUE, NOW()
            )
            ON CONFLICT (vapi_assistant_id) DO NOTHING
        """), {
            "org_id": org_id,
            "aid": assistant_id,
            "name": f"Aria Inbound - {company}",
            "desc": f"Inbound AI answering for {company}",
            "first_msg": first_message[:500],
            "sys_prompt": system_prompt[:2000],
        })
        db.commit()
    except Exception as e:
        logger.debug("vapi_assistants insert skipped (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass

    logger.info(
        "Created Vapi inbound assistant %s for org %s (%s)",
        assistant_id, org_id, company,
    )
    return assistant_id


# ---------------------------------------------------------------------------
# Logging + Task creation helpers
# ---------------------------------------------------------------------------

def _log_inbound_call(
    db: Session,
    from_number: str,
    to_number: str,
    lo_user_id: Optional[int],
    organization_id: Optional[int],
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Log inbound call event to vapi_calls table."""
    call_id = str(uuid.uuid4())
    try:
        db.execute(text("""
            INSERT INTO vapi_calls (
                vapi_call_id, phone_number, direction, status,
                organization_id, call_metadata, created_at
            ) VALUES (
                :call_id, :phone, 'inbound', :status,
                :org_id, :metadata, NOW()
            )
        """), {
            "call_id": call_id,
            "phone": from_number,
            "status": action,
            "org_id": organization_id,
            "metadata": json.dumps(metadata or {}),
        })
        db.commit()
    except Exception as e:
        logger.debug("Failed to log inbound call (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass
    return call_id


def _create_task_for_lo(
    db: Session,
    lo_user_id: int,
    organization_id: Optional[int],
    title: str,
    description: str,
    priority: str = "high",
):
    """Create a task for the LO (callback request, message, etc.)."""
    try:
        db.execute(text("""
            INSERT INTO tasks (
                owner_id, organization_id, title, description,
                priority, status, due_date, created_at, updated_at
            ) VALUES (
                :owner_id, :org_id, :title, :desc,
                :priority, 'pending', :due_date, :now, :now
            )
        """), {
            "owner_id": lo_user_id,
            "org_id": organization_id,
            "title": title[:255],
            "desc": description[:2000],
            "priority": priority,
            "due_date": datetime.now(timezone.utc) + timedelta(hours=1),
            "now": datetime.now(timezone.utc),
        })
        db.commit()
        logger.info("Created task '%s' for LO %s", title, lo_user_id)
    except Exception as e:
        logger.warning("Failed to create task for LO (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


def _log_lead_activity(
    db: Session,
    from_number: str,
    organization_id: Optional[int],
    activity_type: str,
    content: str,
):
    """Log an activity note, associating with a lead if phone matches."""
    try:
        # Find matching lead by phone
        phone_clean = _normalize_phone(from_number)
        lead_id = None
        if phone_clean and len(phone_clean) >= 10:
            lead_row = db.execute(text("""
                SELECT id FROM leads
                WHERE phone LIKE :phone_pattern
                ORDER BY created_at DESC
                LIMIT 1
            """), {"phone_pattern": f"%{phone_clean}"}).fetchone()
            if lead_row:
                lead_id = lead_row.id

        db.execute(text("""
            INSERT INTO activities (
                lead_id, organization_id, type, content, created_at
            ) VALUES (
                :lead_id, :org_id, :type, :content, NOW()
            )
        """), {
            "lead_id": lead_id,
            "org_id": organization_id,
            "type": activity_type,
            "content": content[:2000],
        })
        db.commit()
    except Exception as e:
        logger.debug("Failed to log lead activity (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


def _resolve_org_from_assistant(db: Session, assistant_id: str) -> Optional[Dict[str, Any]]:
    """Look up organization_id and LO from a Vapi assistant ID."""
    if not assistant_id:
        return None
    try:
        row = db.execute(text("""
            SELECT vic.organization_id,
                   u.id AS user_id, u.first_name, u.last_name
            FROM vapi_inbound_configs vic
            LEFT JOIN users u ON u.organization_id = vic.organization_id
                AND u.role IN ('admin', 'loan_officer', 'owner')
            WHERE vic.vapi_assistant_id = :aid
            LIMIT 1
        """), {"aid": assistant_id}).fetchone()
        if row:
            return {
                "organization_id": row.organization_id,
                "user_id": row.user_id,
                "lo_name": f"{row.first_name or ''} {row.last_name or ''}".strip(),
            }
    except Exception as e:
        logger.debug("resolve_org_from_assistant failed: %s", e)
    return None


# ============================================================================
# 1. INBOUND CALL WEBHOOK (Telnyx)
# ============================================================================

@router.post("/inbound-call")
async def inbound_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Telnyx webhook for inbound calls on LO numbers.

    Flow:
      - call.initiated + direction=incoming -> look up LO, decide routing
      - call.hangup with client_state=lo_ring -> LO didn't answer, transfer to Vapi
    """
    try:
        payload = await request.json()
    except Exception as _exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_data = payload.get("data", {})
    event_type = event_data.get("event_type", "")
    event_payload = event_data.get("payload", {})

    # Idempotency check — deduplicate retried Telnyx webhooks via event ID
    _telnyx_event_id = event_data.get("id")
    if _telnyx_event_id:
        from middleware.webhook_idempotency import is_duplicate_webhook
        if is_duplicate_webhook("telnyx", _telnyx_event_id):
            logger.info("Telnyx inbound-call webhook duplicate: event_id=%s", _telnyx_event_id)
            return JSONResponse(status_code=200, content={"status": "duplicate"})

    call_control_id = event_payload.get("call_control_id", "")
    from_number = event_payload.get("from", "")
    to_number = event_payload.get("to", "")
    direction = event_payload.get("direction", "")
    client_state_raw = event_payload.get("client_state", "")

    # Decode client_state (Telnyx base64-encodes it on callbacks)
    client_state = {}
    if client_state_raw:
        try:
            import base64
            decoded = base64.b64decode(client_state_raw).decode("utf-8")
            client_state = json.loads(decoded)
        except Exception as _exc:  # noqa: BLE001
            # Might be plain text/JSON
            logger.exception("unhandled exception")
            if client_state_raw in ("lo_ring",):
                client_state = {"type": client_state_raw}
            else:
                try:
                    client_state = json.loads(client_state_raw)
                except Exception as _exc:  # noqa: BLE001
                    logger.exception("unhandled exception")
                    client_state = {"raw": client_state_raw}

    # --- Handle LO ring timeout / no-answer ---
    if event_type == "call.hangup":
        hangup_cause = event_payload.get("hangup_cause", "")
        state_type = client_state.get("type", "")

        if state_type == "lo_ring" and hangup_cause in (
            "timeout", "no_answer", "originator_cancel", "normal_clearing",
        ):
            # LO didn't answer -- transfer original inbound call to Vapi
            original_ccid = client_state.get("original_ccid", "")
            lo_user_id = client_state.get("lo_id")
            caller_from = client_state.get("from_number", from_number)

            if original_ccid:
                logger.info(
                    "LO ring timeout (cause=%s), forwarding to Vapi. original=%s",
                    hangup_cause, original_ccid[:16],
                )
                lo_info = None
                if lo_user_id:
                    lo_info = {"user_id": lo_user_id}
                    # Fetch org info
                    try:
                        row = db.execute(text("""
                            SELECT u.first_name, u.last_name, u.organization_id,
                                   o.name AS org_name
                            FROM users u
                            LEFT JOIN organizations o ON o.id = u.organization_id
                            WHERE u.id = :uid
                        """), {"uid": lo_user_id}).fetchone()
                        if row:
                            lo_info.update({
                                "full_name": f"{row.first_name or ''} {row.last_name or ''}".strip(),
                                "organization_id": row.organization_id,
                                "org_name": row.org_name or "our team",
                            })
                    except Exception as _exc:  # noqa: BLE001
                        pass

                background_tasks.add_task(
                    _transfer_to_vapi, db, original_ccid, caller_from, lo_info,
                )
                return {"status": "forwarding_to_ai", "hangup_cause": hangup_cause}

        return {"status": "ignored", "event_type": event_type}

    # --- Handle initial inbound call ---
    if event_type != "call.initiated" or direction != "incoming":
        return {"status": "ignored", "event_type": event_type}

    logger.info(
        "Inbound call: from=%s to=%s ccid=%s",
        from_number[-4:] if from_number else "?",
        to_number[-4:] if to_number else "?",
        call_control_id[:16],
    )

    # Step 1: Find the LO
    lo_info = _find_lo_by_phone(db, to_number)
    if not lo_info:
        logger.warning("No LO found for called number %s", to_number[-4:] if to_number else "?")
        await _telnyx_post(f"/calls/{call_control_id}/actions/answer", {})
        await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
            "payload": "Thank you for calling. Please leave a message after the tone.",
            "voice": "female",
            "language": "en-US",
        })
        return {"status": "no_lo_found"}

    org_id = lo_info["organization_id"]
    lo_user_id = lo_info["user_id"]

    # Step 2: Load config
    _ensure_inbound_config_table(db)
    config = _get_inbound_config(db, org_id)
    ring_timeout = config.get("lo_ring_timeout", DEFAULT_LO_RING_TIMEOUT)
    ai_enabled = config.get("ai_answering_enabled", True)
    company_name = config.get("company_name") or lo_info.get("org_name") or "The Tim Loss Team"

    # Step 3: Check availability
    lo_available = _is_lo_available(db, lo_user_id)

    _log_inbound_call(
        db, from_number, to_number, lo_user_id, org_id,
        "lo_available" if lo_available else "lo_unavailable",
        {"lo_name": lo_info["full_name"], "lo_available": lo_available},
    )

    # Step 4: Answer the call
    await _telnyx_post(f"/calls/{call_control_id}/actions/answer", {})

    # Step 5: Route
    if lo_available and lo_info.get("cell_phone"):
        # Ring the LO cell via Telnyx transfer with timeout
        logger.info(
            "Ringing LO %s (user %s) for %ds",
            lo_info["full_name"], lo_user_id, ring_timeout,
        )

        # Speak brief hold message
        await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
            "payload": f"Please hold while I connect you with {lo_info['full_name']}.",
            "voice": "female",
            "language": "en-US",
        })

        # Transfer with timeout -- on no-answer, Telnyx will fire call.hangup
        # with client_state=lo_ring, which we handle above
        lo_cell = lo_info["cell_phone"]
        if not lo_cell.startswith("+"):
            lo_cell = f"+1{_normalize_phone(lo_cell)}"

        await _telnyx_post(f"/calls/{call_control_id}/actions/transfer", {
            "to": lo_cell,
            "from": to_number,
            "timeout_secs": ring_timeout,
            "client_state": json.dumps({
                "type": "lo_ring",
                "original_ccid": call_control_id,
                "lo_id": lo_user_id,
                "from_number": from_number,
            }),
            "webhook_url": f"{API_BASE_URL}/api/v1/telephony/inbound-call",
        })

        return {
            "status": "ringing_lo",
            "lo_name": lo_info["full_name"],
            "timeout": ring_timeout,
        }

    elif ai_enabled:
        # LO unavailable -> hand off to Vapi AI
        logger.info("LO %s unavailable, routing to Vapi AI", lo_info["full_name"])
        background_tasks.add_task(
            _transfer_to_vapi, db, call_control_id, from_number, lo_info,
        )
        return {
            "status": "routing_to_ai",
            "lo_name": lo_info["full_name"],
            "reason": "lo_unavailable" if not lo_available else "no_cell_phone",
        }

    else:
        # AI disabled -- play unavailable message
        await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
            "payload": (
                f"Thank you for calling. {lo_info['full_name']} is currently "
                "unavailable. Please try again later."
            ),
            "voice": "female",
            "language": "en-US",
        })
        return {"status": "unavailable_message"}


# ---------------------------------------------------------------------------
# Vapi transfer helper
# ---------------------------------------------------------------------------

async def _transfer_to_vapi(
    db: Session,
    call_control_id: str,
    from_number: str,
    lo_info: Optional[Dict[str, Any]],
):
    """
    Transfer an active Telnyx call to a Vapi AI assistant.

    Creates a Vapi outbound call to the caller's number, then hangs up
    the Telnyx leg so Vapi takes over the conversation.
    """
    org_id = lo_info.get("organization_id") if lo_info else None
    lo_name = lo_info.get("full_name", "your loan officer") if lo_info else "your loan officer"
    company = lo_info.get("org_name", "our team") if lo_info else "our team"
    lo_user_id = lo_info.get("user_id") if lo_info else None

    # Get or create assistant
    assistant_id = None
    if org_id:
        config = _get_inbound_config(db, org_id)
        assistant_id = config.get("vapi_assistant_id")

        if not assistant_id:
            company_name = config.get("company_name") or company
            assistant_id = await _get_or_create_vapi_assistant(
                db, org_id, lo_name, company_name,
                greeting_override=config.get("greeting_text"),
            )

    if not assistant_id:
        assistant_id = os.getenv("VAPI_DEFAULT_INBOUND_ASSISTANT_ID", "")

    if not assistant_id or not VAPI_API_KEY:
        # Cannot transfer -- speak fallback message
        logger.error("No Vapi assistant available for inbound AI transfer")
        await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
            "payload": (
                f"I'm sorry, {lo_name} is unavailable right now. "
                "Please leave a voicemail after the tone, or call back during business hours."
            ),
            "voice": "female",
            "language": "en-US",
        })
        return

    # Build caller context from CRM data (never blocks the call on failure)
    caller_context = None
    try:
        caller_context = build_inbound_context(db, from_number, org_id)
    except Exception as e:
        logger.warning("Inbound context build failed (non-fatal): %s", e)

    # Build the Vapi call payload with per-call context overrides
    call_payload: Dict[str, Any] = {
        "assistantId": assistant_id,
        "customer": {"number": from_number},
        "metadata": {
            "source": "inbound_transfer",
            "original_call_control_id": call_control_id,
            "lo_user_id": lo_user_id,
            "organization_id": org_id,
        },
    }

    # Inject caller-specific context via assistantOverrides
    if caller_context and caller_context.get("has_context"):
        prompt_addition = caller_context.get("system_prompt_addition", "")
        if prompt_addition:
            call_payload["assistantOverrides"] = {
                "model": {
                    "messages": [
                        {"role": "system", "content": prompt_addition},
                    ],
                },
            }
            lead_data = caller_context.get("lead")
            lead_id = lead_data.get("id") if lead_data else None
            if lead_id:
                call_payload["metadata"]["lead_id"] = lead_id

            # Personalize the first message if we know who's calling
            lead_name = lead_data.get("full_name") if lead_data else None
            if lead_name:
                call_payload["assistantOverrides"]["firstMessage"] = (
                    f"Hi {lead_name}! Thanks for calling back. "
                    f"This is Aria from {company}. How can I help you today?"
                )

            logger.info(
                "Injected inbound context for caller: lead_id=%s",
                lead_id,
            )

    # Create Vapi outbound call to the caller
    try:
        vapi_result = await _vapi_post("/call/phone", call_payload)

        vapi_call_id = vapi_result.get("id")
        if vapi_call_id:
            logger.info(
                "Transferred inbound call to Vapi: assistant=%s call=%s context=%s",
                assistant_id, vapi_call_id,
                "enriched" if (caller_context and caller_context.get("has_context")) else "generic",
            )
            # Hang up the Telnyx leg
            await _telnyx_post(
                f"/calls/{call_control_id}/actions/hangup",
                {"cause": "normal_clearing"},
            )
        else:
            logger.error("Vapi call creation failed: %s", vapi_result)
            # Fallback message
            await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
                "payload": (
                    f"I apologize, {lo_name} is unavailable and our AI assistant "
                    "could not connect. Please try calling back shortly."
                ),
                "voice": "female",
                "language": "en-US",
            })

    except Exception as e:
        logger.error("Failed to transfer to Vapi: %s", e)
        await _telnyx_post(f"/calls/{call_control_id}/actions/speak", {
            "payload": (
                "I apologize for the inconvenience. Please try calling back shortly."
            ),
            "voice": "female",
            "language": "en-US",
        })


# ============================================================================
# 2. VAPI INBOUND WEBHOOK (function-call + end-of-call-report)
# ============================================================================

@router.post("/vapi-inbound-webhook")
async def vapi_inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    raw_body: bytes = Depends(require_vapi_webhook),
    db: Session = Depends(get_db),
):
    """
    Vapi server-side webhook for inbound AI assistant events.

    Handles:
      - function-call: schedule_callback, take_message
      - end-of-call-report: log transcript, summary, create activity
      - status-update: ack
      - assistant-request: return configured assistant ID

    Signature verification is handled by the require_vapi_webhook dependency.
    """
    try:
        payload = json.loads(raw_body)
    except Exception as _exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = payload.get("message", {})
    message_type = message.get("type", "")

    logger.info("Vapi inbound webhook: type=%s", message_type)

    # Idempotency check — deduplicate retried Vapi webhooks.
    # Skip for function-call and assistant-request (synchronous, need fresh response).
    if message_type not in ("function-call", "assistant-request"):
        _inbound_call_id = (
            message.get("call", {}).get("id")
            or payload.get("call", {}).get("id")
        )
        if _inbound_call_id:
            from middleware.webhook_idempotency import is_duplicate_webhook
            if is_duplicate_webhook("vapi", f"inbound:{message_type}:{_inbound_call_id}"):
                logger.info("Vapi inbound webhook duplicate: type=%s call=%s", message_type, _inbound_call_id)
                return JSONResponse(status_code=200, content={"status": "duplicate"})

    # -----------------------------------------------------------------------
    # function-call
    # -----------------------------------------------------------------------
    if message_type == "function-call":
        fn_call = message.get("functionCall", {})
        fn_name = fn_call.get("name", "")
        fn_params = fn_call.get("parameters", {})

        call_data = message.get("call", {})
        call_metadata = call_data.get("metadata", {})
        customer_phone = call_data.get("customer", {}).get("number", "")

        # Resolve org/LO from metadata or assistant ID
        lo_user_id = call_metadata.get("lo_user_id")
        org_id = call_metadata.get("organization_id")

        if not org_id:
            assistant_id = call_data.get("assistantId", "")
            resolved = _resolve_org_from_assistant(db, assistant_id)
            if resolved:
                org_id = resolved["organization_id"]
                lo_user_id = lo_user_id or resolved.get("user_id")

        if fn_name == "schedule_callback":
            caller_name = fn_params.get("caller_name", "Unknown caller")
            caller_phone = fn_params.get("caller_phone") or customer_phone
            preferred_time = fn_params.get("preferred_time", "as soon as possible")
            reason = fn_params.get("reason", "Callback requested via AI")

            if lo_user_id:
                _create_task_for_lo(
                    db,
                    lo_user_id=lo_user_id,
                    organization_id=org_id,
                    title=f"Callback: {caller_name}",
                    description=(
                        f"Phone: {caller_phone}\n"
                        f"Preferred time: {preferred_time}\n"
                        f"Reason: {reason}\n"
                        f"(Taken by Aria AI assistant)"
                    ),
                    priority="high",
                )

            _log_lead_activity(
                db, caller_phone or customer_phone, org_id,
                "AI Callback Scheduled",
                f"Aria scheduled callback for {caller_name}. "
                f"Time: {preferred_time}. Reason: {reason}",
            )

            return {
                "result": (
                    f"I've scheduled a callback for you. {caller_name}, "
                    f"expect to hear from us {preferred_time}."
                )
            }

        elif fn_name == "take_message":
            caller_name = fn_params.get("caller_name", "Unknown caller")
            caller_phone = fn_params.get("caller_phone") or customer_phone
            msg_text = fn_params.get("message", "")

            if lo_user_id:
                _create_task_for_lo(
                    db,
                    lo_user_id=lo_user_id,
                    organization_id=org_id,
                    title=f"Message from {caller_name}",
                    description=(
                        f"Phone: {caller_phone}\n"
                        f"Message: {msg_text}\n"
                        f"(Taken by Aria AI assistant)"
                    ),
                    priority="medium",
                )

            _log_lead_activity(
                db, caller_phone or customer_phone, org_id,
                "AI Message Taken",
                f"Aria took message from {caller_name}: {msg_text}",
            )

            return {
                "result": (
                    f"Message from {caller_name} has been saved. "
                    "Your loan officer will receive it."
                )
            }

        else:
            logger.warning("Unknown function call: %s", fn_name)
            return {
                "result": "I wasn't able to do that. Is there anything else I can help with?"
            }

    # -----------------------------------------------------------------------
    # end-of-call-report
    # -----------------------------------------------------------------------
    elif message_type == "end-of-call-report":
        call_data = message.get("call", {})
        vapi_call_id = call_data.get("id", "")
        call_metadata = call_data.get("metadata", {})
        lo_user_id = call_metadata.get("lo_user_id")
        org_id = call_metadata.get("organization_id")

        transcript = message.get("transcript", "")
        summary = message.get("summary", "")
        recording_url = message.get("recordingUrl", "") or call_data.get("recordingUrl", "")
        stereo_recording_url = call_data.get("stereoRecordingUrl", "")
        ended_reason = message.get("endedReason", "")
        duration = call_data.get("duration")
        customer = call_data.get("customer", {})
        customer_phone = customer.get("number", "")

        # Resolve org from assistant if not in metadata
        if not org_id:
            assistant_id = call_data.get("assistantId", "")
            resolved = _resolve_org_from_assistant(db, assistant_id)
            if resolved:
                org_id = resolved["organization_id"]
                lo_user_id = lo_user_id or resolved.get("user_id")

        # Upsert into vapi_calls
        _rec_status = "available" if recording_url else "none"
        _tx_status = "completed" if transcript else "none"
        try:
            db.execute(text("""
                INSERT INTO vapi_calls (
                    vapi_call_id, phone_number, direction, status,
                    transcript, summary, recording_url, stereo_recording_url,
                    recording_status, transcript_status,
                    duration, organization_id, call_metadata,
                    started_at, ended_at, created_at
                ) VALUES (
                    :call_id, :phone, 'inbound', 'completed',
                    :transcript, :summary, :recording_url, :stereo_recording_url,
                    :recording_status, :transcript_status,
                    :duration, :org_id, :metadata,
                    :started, :ended, NOW()
                )
                ON CONFLICT (vapi_call_id)
                DO UPDATE SET
                    status = 'completed',
                    transcript = EXCLUDED.transcript,
                    summary = EXCLUDED.summary,
                    recording_url = EXCLUDED.recording_url,
                    stereo_recording_url = EXCLUDED.stereo_recording_url,
                    recording_status = EXCLUDED.recording_status,
                    transcript_status = EXCLUDED.transcript_status,
                    duration = EXCLUDED.duration,
                    ended_at = EXCLUDED.ended_at,
                    updated_at = NOW()
            """), {
                "call_id": vapi_call_id or str(uuid.uuid4()),
                "phone": customer_phone,
                "transcript": transcript[:10000] if transcript else None,
                "summary": summary[:2000] if summary else None,
                "recording_url": recording_url or None,
                "stereo_recording_url": stereo_recording_url or None,
                "recording_status": _rec_status,
                "transcript_status": _tx_status,
                "duration": duration,
                "org_id": org_id,
                "metadata": json.dumps(call_metadata),
                "started": call_data.get("startedAt"),
                "ended": call_data.get("endedAt"),
            })
            db.commit()
        except Exception as e:
            logger.warning("Failed to log end-of-call report: %s", e)
            try:
                db.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass

        # Log activity
        activity_content = f"AI Inbound Call Summary:\n{summary or 'No summary available.'}"
        if transcript:
            activity_content += f"\n\nTranscript (excerpt):\n{transcript[:500]}"

        _log_lead_activity(
            db, customer_phone, org_id,
            "AI Inbound Call",
            activity_content,
        )

        # Call intelligence integration
        try:
            from services.call_intelligence.integration import handle_vapi_call_ended as _handle_ci
            if _handle_ci:
                ci_call_data = {
                    "messages": [{"role": "assistant", "message": transcript}] if transcript else [],
                    "assistant": {"metadata": {"organization_id": org_id}},
                    "duration": duration,
                }
                background_tasks.add_task(
                    _handle_ci, db, vapi_call_id, ci_call_data,
                )
        except ImportError:
            pass

        logger.info(
            "End-of-call processed: call=%s duration=%s reason=%s",
            vapi_call_id[:16] if vapi_call_id else "?", duration, ended_reason,
        )
        return {"status": "received"}

    # -----------------------------------------------------------------------
    # status-update
    # -----------------------------------------------------------------------
    elif message_type == "status-update":
        status = message.get("status", "")
        logger.debug("Vapi status update: %s", status)
        return {"status": "received"}

    # -----------------------------------------------------------------------
    # assistant-request (dynamic routing)
    # -----------------------------------------------------------------------
    elif message_type == "assistant-request":
        call_data = message.get("call", {})
        call_metadata = call_data.get("metadata", {})
        org_id = call_metadata.get("organization_id")

        if org_id:
            config = _get_inbound_config(db, org_id)
            aid = config.get("vapi_assistant_id")
            if aid:
                return {"assistantId": aid}

        default_aid = os.getenv("VAPI_DEFAULT_INBOUND_ASSISTANT_ID", "")
        if default_aid:
            return {"assistantId": default_aid}

        return {
            "assistant": {
                "name": "Aria - Default Inbound",
                "model": {
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5-20251001",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are Aria, an AI assistant for The Tim Loss Team. "
                                "You're a mortgage loan officer's virtual receptionist.\n\n"
                                "Your role:\n"
                                "- Greet callers warmly and professionally\n"
                                "- Answer basic mortgage questions\n"
                                "- Offer to schedule a callback with the loan officer\n"
                                "- Take messages\n\n"
                                "Rules:\n"
                                "- Never provide specific rate quotes\n"
                                "- Never give legal or tax advice\n"
                                "- Be concise — this is a phone call\n"
                                "- Always confirm the caller's name and number before ending"
                            ),
                        }
                    ],
                },
                "voice": {
                    "provider": "deepgram",
                    "voiceId": "asteria",
                },
                "firstMessage": (
                    "Hi, thanks for calling! This is Aria. How can I help you today?"
                ),
                "silenceTimeoutSeconds": 30,
                "maxDurationSeconds": 300,
            }
        }

    else:
        logger.debug("Unhandled Vapi webhook type: %s", message_type)
        return {"status": "received"}


# ============================================================================
# 3. INBOUND CONFIG CRUD
# ============================================================================

@router.get("/inbound-config")
async def get_inbound_config_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get inbound AI answering configuration for the current org."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    _ensure_inbound_config_table(db)
    config = _get_inbound_config(db, org_id)
    return config


@router.put("/inbound-config")
async def update_inbound_config_endpoint(
    body: InboundConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Update inbound AI answering configuration."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    _ensure_inbound_config_table(db)

    now = datetime.now(timezone.utc)

    # Build dynamic update
    updates: List[str] = []
    params: Dict[str, Any] = {"org_id": org_id, "now": now}

    if body.ai_answering_enabled is not None:
        updates.append("ai_answering_enabled = :enabled")
        params["enabled"] = body.ai_answering_enabled
    if body.greeting_text is not None:
        updates.append("greeting_text = :greeting")
        params["greeting"] = body.greeting_text
    if body.lo_ring_timeout is not None:
        updates.append("lo_ring_timeout = :timeout")
        params["timeout"] = body.lo_ring_timeout
    if body.vapi_assistant_id is not None:
        updates.append("vapi_assistant_id = :aid")
        params["aid"] = body.vapi_assistant_id
    if body.company_name is not None:
        updates.append("company_name = :company")
        params["company"] = body.company_name

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = :now")
    set_clause = ", ".join(updates)

    try:
        existing = db.execute(text(
            "SELECT id FROM vapi_inbound_configs WHERE organization_id = :org_id"
        ), {"org_id": org_id}).fetchone()

        if existing:
            sql = "UPDATE vapi_inbound_configs SET " + set_clause + " WHERE organization_id = :org_id"
            db.execute(text(sql), params)
        else:
            db.execute(text("""
                INSERT INTO vapi_inbound_configs (
                    organization_id, ai_answering_enabled, greeting_text,
                    lo_ring_timeout, vapi_assistant_id, company_name,
                    created_at, updated_at
                ) VALUES (
                    :org_id,
                    :enabled, :greeting, :timeout, :aid, :company,
                    :now, :now
                )
            """), {
                "org_id": org_id,
                "enabled": body.ai_answering_enabled if body.ai_answering_enabled is not None else True,
                "greeting": body.greeting_text,
                "timeout": body.lo_ring_timeout or DEFAULT_LO_RING_TIMEOUT,
                "aid": body.vapi_assistant_id,
                "company": body.company_name,
                "now": now,
            })

        db.commit()
    except Exception as e:
        logger.error("Failed to update inbound config: %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    config = _get_inbound_config(db, org_id)
    return {"status": "updated", "config": config}


@router.post("/inbound-config/provision-assistant")
async def provision_inbound_assistant(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """
    Provision (or re-provision) the Vapi inbound assistant for this org.

    Creates a new Vapi assistant with current LO name and company info.
    Useful after changing greeting text or LO configuration.
    """
    org_id = _get_org_id(current_user)
    user_id = _get_user_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    _ensure_inbound_config_table(db)

    # Get LO and org info
    row = db.execute(text("""
        SELECT u.first_name, u.last_name, o.name AS org_name
        FROM users u
        LEFT JOIN organizations o ON o.id = u.organization_id
        WHERE u.id = :user_id
    """), {"user_id": user_id}).fetchone()

    lo_name = f"{row.first_name or ''} {row.last_name or ''}".strip() if row else "your loan officer"
    company = row.org_name if row else "our team"

    config = _get_inbound_config(db, org_id)
    company_name = config.get("company_name") or company

    # Clear existing assistant so a fresh one is created
    try:
        db.execute(text("""
            UPDATE vapi_inbound_configs
            SET vapi_assistant_id = NULL, updated_at = NOW()
            WHERE organization_id = :org_id
        """), {"org_id": org_id})
        db.commit()
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass

    assistant_id = await _get_or_create_vapi_assistant(
        db, org_id, lo_name, company_name,
        greeting_override=config.get("greeting_text"),
    )

    if not assistant_id:
        raise HTTPException(status_code=502, detail="Failed to create Vapi assistant")

    return {
        "status": "success",
        "vapi_assistant_id": assistant_id,
        "lo_name": lo_name,
        "company_name": company_name,
    }


# ============================================================================
# 4. MIGRATION ENDPOINT
# ============================================================================

@router.post("/inbound-config/migrate")
async def run_inbound_migration(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Create the vapi_inbound_configs table if it does not exist."""
    _ensure_inbound_config_table(db)
    return {"status": "success", "message": "vapi_inbound_configs table ready"}
