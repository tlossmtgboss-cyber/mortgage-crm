"""
Natural Language IVR Routes
============================
Deeper Vapi integration for intelligent call routing using natural language
intent detection instead of DTMF-only menus.

Endpoints:
  - GET/PUT  /api/v1/nl-ivr/config          — per-org NL IVR configuration
  - POST     /api/v1/nl-ivr/create-assistant — create/update Vapi assistant for IVR
  - GET      /api/v1/nl-ivr/assistant-status — check current Vapi assistant status
  - POST     /api/v1/nl-ivr/vapi-webhook     — handle Vapi function calls (unauthenticated)
  - POST     /api/v1/nl-ivr/test-lookup      — test borrower phone lookup (authenticated)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db, get_async_db
from routes.auth_deps import current_user_flexible_dep
from middleware.webhook_verification import require_vapi_webhook
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import httpx
import os
import json
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/nl-ivr", tags=["NL IVR"])

VAPI_API_BASE = "https://api.vapi.ai"

# Human-readable stage descriptions for IVR callers
STAGE_DESCRIPTIONS = {
    "APPLICATION": "Your application has been received and is being reviewed.",
    "DISCLOSED": "Your initial disclosures have been sent. Please review and sign them.",
    "PROCESSING": "Your loan file is being processed. We may reach out for additional documents.",
    "SUBMITTED": "Your file has been submitted to underwriting.",
    "UNDERWRITING": "Your loan is currently under review by the underwriting team.",
    "UW_RECEIVED": "Underwriting has received your file and is reviewing it.",
    "CONDITIONAL_APPROVAL": "You have received a conditional approval. We need a few more items.",
    "APPROVED": "Congratulations, your loan has been approved!",
    "SUSPENDED": "Your file has been temporarily suspended. Your loan officer will contact you.",
    "CTC": "You are clear to close. We are preparing your closing documents.",
    "CLEAR_TO_CLOSE": "You are clear to close. Closing documents are being prepared.",
    "CLOSING": "Your loan is in the closing process.",
    "DOCS": "Your closing documents are being prepared.",
    "DOCS_OUT": "Your closing documents have been sent for signing.",
    "FUNDED": "Your loan has been funded. Congratulations!",
    "CANCELLED": "This loan file has been cancelled.",
    "DENIED": "Unfortunately, this loan application was not approved.",
    "NURTURE": "We are keeping your file active for when you are ready to proceed.",
}


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class IVRMenuOption(BaseModel):
    intent: str = Field(..., description="Intent keyword, e.g. 'loan_status'")
    description: str = Field(..., description="Human description, e.g. 'Check my loan status'")
    action: str = Field(..., description="Action: route_department, lookup_loan, schedule_callback, transfer_lo, take_message, custom")
    department: Optional[str] = None
    transfer_number: Optional[str] = None


class NLIVRConfig(BaseModel):
    greeting: str = "Thank you for calling. I'm an AI assistant and I can help you with your mortgage questions. How can I help you today?"
    menu_options: List[IVRMenuOption] = []
    fallback_action: str = "take_message"
    max_retries: int = 2
    language: str = "en"
    business_name: Optional[str] = None
    business_hours: Optional[str] = None
    after_hours_greeting: Optional[str] = None


class NLIVRConfigUpdate(BaseModel):
    greeting: Optional[str] = None
    menu_options: Optional[List[IVRMenuOption]] = None
    fallback_action: Optional[str] = None
    max_retries: Optional[int] = None
    language: Optional[str] = None
    business_name: Optional[str] = None
    business_hours: Optional[str] = None
    after_hours_greeting: Optional[str] = None


class CreateAssistantRequest(BaseModel):
    """Optional overrides when creating the Vapi assistant."""
    first_message: Optional[str] = None
    voice_provider: Optional[str] = "deepgram"
    voice_id: Optional[str] = "asteria"


# =============================================================================
# TABLE BOOTSTRAP
# =============================================================================

def _ensure_nl_ivr_table(db: Session):
    """Create the nl_ivr_configs table if it does not exist."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS nl_ivr_configs (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE,
                greeting TEXT,
                menu_options JSONB DEFAULT '[]'::jsonb,
                fallback_action VARCHAR(50) DEFAULT 'take_message',
                max_retries INTEGER DEFAULT 2,
                language VARCHAR(10) DEFAULT 'en',
                business_name VARCHAR(255),
                business_hours VARCHAR(255),
                after_hours_greeting TEXT,
                vapi_assistant_id VARCHAR(255),
                vapi_phone_number_id VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"nl_ivr_configs table check: {e}")


# =============================================================================
# IVR CONFIGURATION ENDPOINTS
# =============================================================================

@router.get("/config")
async def get_nl_ivr_config(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get the NL IVR configuration for the current user's organization."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_nl_ivr_table(db)

    row = await db.execute(text("""
        SELECT id, organization_id, greeting, menu_options, fallback_action,
               max_retries, language, business_name, business_hours,
               after_hours_greeting, vapi_assistant_id, vapi_phone_number_id,
               created_at, updated_at
        FROM nl_ivr_configs
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    if not row:
        # Return defaults with default menu options
        return {
            "configured": False,
            "config": _default_config(),
            "vapi_assistant_id": None,
        }

    return {
        "configured": True,
        "config": {
            "greeting": row.greeting,
            "menu_options": row.menu_options or [],
            "fallback_action": row.fallback_action,
            "max_retries": row.max_retries,
            "language": row.language,
            "business_name": row.business_name,
            "business_hours": row.business_hours,
            "after_hours_greeting": row.after_hours_greeting,
        },
        "vapi_assistant_id": row.vapi_assistant_id,
        "vapi_phone_number_id": row.vapi_phone_number_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/config")
async def update_nl_ivr_config(
    body: NLIVRConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Create or update the NL IVR configuration for the current user's organization."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_nl_ivr_table(db)

    existing = await db.execute(text(
        "SELECT id FROM nl_ivr_configs WHERE organization_id = :org_id"
    ), {"org_id": org_id}).fetchone()

    # Serialize menu_options for JSONB storage
    menu_options_json = None
    if body.menu_options is not None:
        menu_options_json = json.dumps([opt.dict() for opt in body.menu_options])

    if existing:
        # Build dynamic UPDATE
        updates = []
        params: Dict[str, Any] = {"org_id": org_id}

        if body.greeting is not None:
            updates.append("greeting = :greeting")
            params["greeting"] = body.greeting
        if menu_options_json is not None:
            updates.append("menu_options = :menu_options::jsonb")
            params["menu_options"] = menu_options_json
        if body.fallback_action is not None:
            updates.append("fallback_action = :fallback_action")
            params["fallback_action"] = body.fallback_action
        if body.max_retries is not None:
            updates.append("max_retries = :max_retries")
            params["max_retries"] = body.max_retries
        if body.language is not None:
            updates.append("language = :language")
            params["language"] = body.language
        if body.business_name is not None:
            updates.append("business_name = :business_name")
            params["business_name"] = body.business_name
        if body.business_hours is not None:
            updates.append("business_hours = :business_hours")
            params["business_hours"] = body.business_hours
        if body.after_hours_greeting is not None:
            updates.append("after_hours_greeting = :after_hours_greeting")
            params["after_hours_greeting"] = body.after_hours_greeting

        updates.append("updated_at = NOW()")

        if updates:
            update_sql = "UPDATE nl_ivr_configs SET " + ', '.join(updates) + " WHERE organization_id = :org_id"
            await db.execute(text(update_sql), params)
            await db.commit()
    else:
        # INSERT new config
        defaults = _default_config()
        await db.execute(text("""
            INSERT INTO nl_ivr_configs
                (organization_id, greeting, menu_options, fallback_action,
                 max_retries, language, business_name, business_hours, after_hours_greeting)
            VALUES
                (:org_id, :greeting, :menu_options::jsonb, :fallback_action,
                 :max_retries, :language, :business_name, :business_hours, :after_hours_greeting)
        """), {
            "org_id": org_id,
            "greeting": body.greeting or defaults["greeting"],
            "menu_options": menu_options_json or json.dumps(defaults["menu_options"]),
            "fallback_action": body.fallback_action or defaults["fallback_action"],
            "max_retries": body.max_retries if body.max_retries is not None else defaults["max_retries"],
            "language": body.language or defaults["language"],
            "business_name": body.business_name,
            "business_hours": body.business_hours,
            "after_hours_greeting": body.after_hours_greeting,
        })
        await db.commit()

    return {"success": True, "message": "NL IVR configuration saved"}


# =============================================================================
# VAPI ASSISTANT MANAGEMENT
# =============================================================================

@router.post("/create-assistant")
async def create_vapi_ivr_assistant(
    body: CreateAssistantRequest = CreateAssistantRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Create or update the Vapi assistant configured as a Natural Language IVR."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    vapi_key = os.getenv("VAPI_API_KEY")
    if not vapi_key:
        raise HTTPException(status_code=503, detail="VAPI_API_KEY not configured")

    _ensure_nl_ivr_table(db)

    # Load org config (or defaults)
    row = await db.execute(text("""
        SELECT greeting, menu_options, fallback_action, max_retries,
               language, business_name, vapi_assistant_id
        FROM nl_ivr_configs
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    if row:
        config = {
            "greeting": row.greeting,
            "menu_options": row.menu_options or [],
            "fallback_action": row.fallback_action,
            "max_retries": row.max_retries or 2,
            "language": row.language or "en",
            "business_name": row.business_name,
        }
        existing_assistant_id = row.vapi_assistant_id
    else:
        config = _default_config()
        existing_assistant_id = None

    # Build the system prompt incorporating configured intents
    system_prompt = _build_system_prompt(config)

    # Build Vapi function tool definitions
    tools = _build_vapi_tools()

    webhook_url = os.getenv("BASE_URL", "https://api.perenniaai.com")
    if not webhook_url.startswith("http"):
        webhook_url = f"https://{webhook_url}"

    assistant_payload = {
        "name": f"NL-IVR-{org_id}",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
            "tools": tools,
        },
        "voice": {
            "provider": body.voice_provider or "deepgram",
            "voiceId": body.voice_id or "asteria",
        },
        "firstMessage": body.first_message or config.get("greeting", "How can I help you today?"),
        "serverUrl": f"{webhook_url}/api/v1/nl-ivr/vapi-webhook",
        "endCallFunctionEnabled": True,
        "silenceTimeoutSeconds": 15,
        "maxDurationSeconds": 300,
        "metadata": {
            "organization_id": org_id,
            "type": "nl_ivr",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Bearer {vapi_key}",
                "Content-Type": "application/json",
            }

            if existing_assistant_id:
                # Update existing assistant
                resp = await client.patch(
                    f"{VAPI_API_BASE}/assistant/{existing_assistant_id}",
                    headers=headers,
                    json=assistant_payload,
                )
            else:
                # Create new assistant
                resp = await client.post(
                    f"{VAPI_API_BASE}/assistant",
                    headers=headers,
                    json=assistant_payload,
                )

            if resp.status_code not in (200, 201):
                logger.error(f"Vapi assistant API error: {resp.status_code} {resp.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Vapi API returned {resp.status_code}",
                )

            vapi_data = resp.json()
            assistant_id = vapi_data.get("id")

    except httpx.HTTPError as e:
        logger.error(f"Vapi HTTP error creating assistant: {e}")
        raise HTTPException(status_code=502, detail="Failed to reach Vapi API")

    # Persist assistant ID
    if row:
        await db.execute(text("""
            UPDATE nl_ivr_configs
            SET vapi_assistant_id = :assistant_id, updated_at = NOW()
            WHERE organization_id = :org_id
        """), {"assistant_id": assistant_id, "org_id": org_id})
    else:
        defaults = _default_config()
        await db.execute(text("""
            INSERT INTO nl_ivr_configs
                (organization_id, greeting, menu_options, fallback_action,
                 max_retries, language, vapi_assistant_id)
            VALUES
                (:org_id, :greeting, :menu_options::jsonb, :fallback, :retries, :lang, :assistant_id)
        """), {
            "org_id": org_id,
            "greeting": defaults["greeting"],
            "menu_options": json.dumps(defaults["menu_options"]),
            "fallback": defaults["fallback_action"],
            "retries": defaults["max_retries"],
            "lang": defaults["language"],
            "assistant_id": assistant_id,
        })
    await db.commit()

    return {
        "success": True,
        "assistant_id": assistant_id,
        "message": "Vapi NL IVR assistant created" if not existing_assistant_id else "Vapi NL IVR assistant updated",
    }


@router.get("/assistant-status")
async def get_assistant_status(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Check the current Vapi assistant status for this org."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_nl_ivr_table(db)

    row = await db.execute(text("""
        SELECT vapi_assistant_id, vapi_phone_number_id, updated_at
        FROM nl_ivr_configs WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    if not row or not row.vapi_assistant_id:
        return {"configured": False, "assistant_id": None}

    # Optionally ping Vapi to verify the assistant still exists
    vapi_key = os.getenv("VAPI_API_KEY")
    vapi_status = "unknown"
    if vapi_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{VAPI_API_BASE}/assistant/{row.vapi_assistant_id}",
                    headers={"Authorization": f"Bearer {vapi_key}"},
                )
                vapi_status = "active" if resp.status_code == 200 else "not_found"
        except Exception as e:
            logger.warning(f"Could not verify Vapi assistant: {e}")
            vapi_status = "unreachable"

    return {
        "configured": True,
        "assistant_id": row.vapi_assistant_id,
        "phone_number_id": row.vapi_phone_number_id,
        "vapi_status": vapi_status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# =============================================================================
# VAPI WEBHOOK HANDLER (UNAUTHENTICATED -- called by Vapi servers)
# =============================================================================

@router.post("/vapi-webhook")
async def vapi_ivr_webhook(
    request: Request,
    raw_body: bytes = Depends(require_vapi_webhook),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Handle Vapi server-side function call events for the NL IVR assistant.

    Vapi sends a POST with the function call details. We execute the function
    and return the result so the assistant can continue the conversation.
    Signature verification is handled by the require_vapi_webhook dependency.
    """
    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.error(f"NL IVR webhook: invalid JSON: {e}")
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message_type = payload.get("message", {}).get("type", "")
    logger.info(f"NL IVR webhook received: type={message_type}")

    # Handle function-call messages
    if message_type == "function-call":
        fn_call = payload.get("message", {}).get("functionCall", {})
        fn_name = fn_call.get("name", "")
        fn_params = fn_call.get("parameters", {})

        # Extract org ID from assistant metadata
        assistant_meta = payload.get("message", {}).get("call", {}).get("assistantId")
        org_id = _resolve_org_from_payload(payload, db)

        # Caller phone from the call object
        caller_phone = (
            payload.get("message", {}).get("call", {}).get("customer", {}).get("number", "")
        )

        logger.info(f"NL IVR function call: {fn_name} params={fn_params} org={org_id} caller={caller_phone}")

        result = _handle_function_call(
            fn_name, fn_params, org_id, caller_phone, db
        )

        return JSONResponse({"result": result})

    # Handle end-of-call-report for logging
    if message_type == "end-of-call-report":
        _log_call_report(payload, db)
        return JSONResponse({"ok": True})

    # Handle status-update, hang, etc. -- acknowledge
    return JSONResponse({"ok": True})


# =============================================================================
# TEST / DEBUG ENDPOINT
# =============================================================================

@router.post("/test-lookup")
async def test_borrower_lookup(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Test the borrower phone lookup logic (authenticated, for debugging)."""
    data = await request.json()
    phone = data.get("phone", "")
    if not phone:
        raise HTTPException(status_code=400, detail="phone is required")

    org_id = getattr(current_user, "organization_id", None)
    result = _lookup_loan_status_by_phone(phone, org_id, db)
    return result


# =============================================================================
# INTERNAL: FUNCTION CALL DISPATCHER
# =============================================================================

def _handle_function_call(
    fn_name: str,
    params: Dict[str, Any],
    org_id: Optional[int],
    caller_phone: str,
    db: Session,
) -> str:
    """Dispatch a Vapi function call to the appropriate handler. Returns a string for the assistant."""
    try:
        if fn_name == "route_to_department":
            return _fn_route_to_department(params, org_id, db)
        elif fn_name == "lookup_loan_status":
            return _fn_lookup_loan_status(params, org_id, caller_phone, db)
        elif fn_name == "schedule_callback":
            return _fn_schedule_callback(params, org_id, caller_phone, db)
        elif fn_name == "transfer_to_lo":
            return _fn_transfer_to_lo(params, org_id, caller_phone, db)
        elif fn_name == "take_message":
            return _fn_take_message(params, org_id, caller_phone, db)
        else:
            logger.warning(f"Unknown NL IVR function: {fn_name}")
            return "I'm sorry, I wasn't able to process that request. Let me take a message instead."
    except Exception as e:
        logger.exception(f"Error in NL IVR function {fn_name}: {e}")
        return "I apologize, but I encountered an error. Please hold while I connect you to someone who can help."


# =============================================================================
# FUNCTION IMPLEMENTATIONS
# =============================================================================

def _fn_route_to_department(params: Dict, org_id: Optional[int], db: Session) -> str:
    """Route caller to a department based on intent."""
    department = params.get("department", "general")

    # Look up configured routing from the NL IVR menu_options
    if org_id:
        config_row = db.execute(text("""
            SELECT menu_options FROM nl_ivr_configs WHERE organization_id = :org_id
        """), {"org_id": org_id}).fetchone()

        if config_row and config_row.menu_options:
            for opt in config_row.menu_options:
                if isinstance(opt, dict) and opt.get("intent") == department:
                    if opt.get("transfer_number"):
                        return json.dumps({
                            "action": "transfer",
                            "destination": opt["transfer_number"],
                            "message": f"I'll connect you to our {opt.get('description', department)} team now.",
                        })

    # Default department mapping
    dept_messages = {
        "sales": "I'll connect you with our loan origination team.",
        "processing": "I'll connect you with our loan processing team.",
        "support": "I'll connect you with our support team.",
        "rates": "Let me get you current rate information.",
        "general": "Let me connect you with someone who can help.",
    }

    return dept_messages.get(department, dept_messages["general"])


def _fn_lookup_loan_status(
    params: Dict, org_id: Optional[int], caller_phone: str, db: Session
) -> str:
    """Look up loan status. Privacy: verify caller phone matches borrower phone."""
    # The caller may provide their name or loan number for additional verification
    borrower_name = params.get("borrower_name", "")
    loan_number = params.get("loan_number", "")

    # Normalize phone for matching
    normalized_phone = _normalize_phone(caller_phone)
    if not normalized_phone and not loan_number:
        return "I need to verify your identity. Could you please provide your loan number?"

    result = _lookup_loan_status_by_phone(
        caller_phone, org_id, db,
        borrower_name=borrower_name,
        loan_number=loan_number,
    )

    if not result.get("found"):
        return result.get("message", "I wasn't able to locate your loan. Could you provide your loan number?")

    loan = result["loan"]
    stage_desc = STAGE_DESCRIPTIONS.get(loan["stage"], "Your loan is being processed.")

    parts = [f"I found your loan. Here's your status update:"]
    parts.append(stage_desc)
    if loan.get("lo_name"):
        parts.append(f"Your loan officer is {loan['lo_name']}.")
    if loan.get("closing_date"):
        parts.append(f"Your expected closing date is {loan['closing_date']}.")
    if loan.get("next_step"):
        parts.append(f"Next step: {loan['next_step']}")

    return " ".join(parts)


def _fn_schedule_callback(
    params: Dict, org_id: Optional[int], caller_phone: str, db: Session
) -> str:
    """Schedule a callback by creating a task for the assigned LO."""
    caller_name = params.get("caller_name", "IVR Caller")
    preferred_time = params.get("preferred_time", "")
    reason = params.get("reason", "Callback requested via IVR")

    # Try to find the borrower's LO
    lo_id = None
    loan_id = None
    normalized = _normalize_phone(caller_phone)

    if normalized and org_id:
        loan_row = db.execute(text("""
            SELECT l.id, l.loan_officer_id, l.loan_number
            FROM loans l
            WHERE l.borrower_phone LIKE :phone_pattern
              AND l.organization_id = :org_id
              AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
            ORDER BY l.created_at DESC
            LIMIT 1
        """), {"phone_pattern": f"%{normalized[-10:]}%", "org_id": org_id}).fetchone()

        if loan_row:
            lo_id = loan_row.loan_officer_id
            loan_id = loan_row.id

    # Parse preferred time into a due date
    due_date = datetime.now(timezone.utc) + timedelta(hours=1)
    if preferred_time:
        # Simple heuristic: if they say "tomorrow", add a day
        if "tomorrow" in preferred_time.lower():
            due_date = datetime.now(timezone.utc) + timedelta(days=1)
        elif "afternoon" in preferred_time.lower():
            due_date = due_date.replace(hour=14, minute=0)
        elif "morning" in preferred_time.lower():
            due_date = due_date.replace(hour=10, minute=0)

    try:
        db.execute(text("""
            INSERT INTO tasks
                (organization_id, title, description, status, priority,
                 due_date, owner_id, loan_id, related_contact_name, related_type, created_at, updated_at)
            VALUES
                (:org_id, :title, :description, 'pending', 'high',
                 :due_date, :owner_id, :loan_id, :contact_name, 'ivr_callback', NOW(), NOW())
        """), {
            "org_id": org_id,
            "title": f"IVR Callback: {caller_name}",
            "description": f"Callback requested via NL IVR. Phone: {caller_phone}. Reason: {reason}. Preferred time: {preferred_time or 'ASAP'}",
            "due_date": due_date,
            "owner_id": lo_id,
            "loan_id": loan_id,
            "contact_name": caller_name,
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to create callback task: {e}")
        db.rollback()
        return "I apologize, but I had trouble scheduling your callback. Please try calling back during business hours."

    time_str = "as soon as possible" if not preferred_time else preferred_time
    return f"I've scheduled a callback for {time_str}. Your loan officer will reach out to you at {caller_phone}. Is there anything else I can help with?"


def _fn_transfer_to_lo(
    params: Dict, org_id: Optional[int], caller_phone: str, db: Session
) -> str:
    """Attempt to transfer the caller to their assigned loan officer."""
    normalized = _normalize_phone(caller_phone)

    if not normalized or not org_id:
        return "I'm unable to look up your loan officer right now. Let me take a message instead."

    # Find the LO for this borrower
    lo_row = db.execute(text("""
        SELECT u.id, u.first_name, u.last_name, u.phone as user_phone,
               u.cell_phone, u.office_phone
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.borrower_phone LIKE :phone_pattern
          AND l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
        ORDER BY l.created_at DESC
        LIMIT 1
    """), {"phone_pattern": f"%{normalized[-10:]}%", "org_id": org_id}).fetchone()

    if not lo_row:
        return "I wasn't able to find your assigned loan officer. Let me take a message and have someone call you back."

    lo_name = f"{lo_row.first_name or ''} {lo_row.last_name or ''}".strip()
    lo_phone = lo_row.cell_phone or lo_row.office_phone or lo_row.user_phone

    if not lo_phone:
        return f"Your loan officer is {lo_name}, but I'm unable to transfer you directly right now. I'll schedule a callback instead."

    # Return transfer instruction for the Vapi assistant
    return json.dumps({
        "action": "transfer",
        "destination": lo_phone,
        "message": f"I'm transferring you to your loan officer, {lo_name}, now. Please hold.",
    })


def _fn_take_message(
    params: Dict, org_id: Optional[int], caller_phone: str, db: Session
) -> str:
    """Log a message as an activity tied to the borrower's lead/loan."""
    caller_name = params.get("caller_name", "Unknown Caller")
    message_text = params.get("message", "No message provided")

    # Try to find matching lead or loan
    lead_id = None
    loan_id = None
    normalized = _normalize_phone(caller_phone)

    if normalized and org_id:
        # Check leads first
        lead_row = db.execute(text("""
            SELECT id FROM leads
            WHERE phone LIKE :phone_pattern AND organization_id = :org_id
            ORDER BY created_at DESC LIMIT 1
        """), {"phone_pattern": f"%{normalized[-10:]}%", "org_id": org_id}).fetchone()

        if lead_row:
            lead_id = lead_row.id

        # Check loans
        loan_row = db.execute(text("""
            SELECT id FROM loans
            WHERE borrower_phone LIKE :phone_pattern AND organization_id = :org_id
            ORDER BY created_at DESC LIMIT 1
        """), {"phone_pattern": f"%{normalized[-10:]}%", "org_id": org_id}).fetchone()

        if loan_row:
            loan_id = loan_row.id

    try:
        db.execute(text("""
            INSERT INTO activities
                (organization_id, type, content, lead_id, loan_id, user_metadata, created_at)
            VALUES
                (:org_id, 'Call', :content, :lead_id, :loan_id, :metadata, NOW())
        """), {
            "org_id": org_id,
            "content": f"IVR Message from {caller_name} ({caller_phone}): {message_text}",
            "lead_id": lead_id,
            "loan_id": loan_id,
            "metadata": json.dumps({"source": "nl_ivr", "caller_phone": caller_phone}),
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log IVR message: {e}")
        db.rollback()
        return "I had trouble saving your message, but I'll make sure someone follows up with you."

    return "I've recorded your message and someone from our team will get back to you shortly. Is there anything else I can help with?"


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _normalize_phone(phone: str) -> str:
    """Strip a phone number to digits only."""
    if not phone:
        return ""
    return re.sub(r"[^\d]", "", phone)


def _resolve_org_from_payload(payload: Dict, db: Session) -> Optional[int]:
    """Extract organization_id from Vapi webhook payload metadata."""
    # Try assistant metadata first
    meta = payload.get("message", {}).get("call", {}).get("assistant", {}).get("metadata", {})
    org_id = meta.get("organization_id")
    if org_id:
        return int(org_id)

    # Try looking up by assistant ID
    assistant_id = payload.get("message", {}).get("call", {}).get("assistantId")
    if assistant_id:
        row = db.execute(text(
            "SELECT organization_id FROM nl_ivr_configs WHERE vapi_assistant_id = :aid"
        ), {"aid": assistant_id}).fetchone()
        if row:
            return row.organization_id

    return None


def _lookup_loan_status_by_phone(
    phone: str,
    org_id: Optional[int],
    db: Session,
    borrower_name: str = "",
    loan_number: str = "",
) -> Dict[str, Any]:
    """Look up loan status by borrower phone with privacy verification."""
    normalized = _normalize_phone(phone)

    # If loan number provided, look up directly
    if loan_number:
        filters = ["l.loan_number = :loan_number"]
        params: Dict[str, Any] = {"loan_number": loan_number}
        if org_id:
            filters.append("l.organization_id = :org_id")
            params["org_id"] = org_id

        loan_sql = (
            "SELECT l.id, l.loan_number, l.stage, l.borrower_name, l.borrower_phone,"
            "       l.closing_date, l.loan_officer_name,"
            "       CONCAT(u.first_name, ' ', u.last_name) as lo_name"
            " FROM loans l"
            " LEFT JOIN users u ON u.id = l.loan_officer_id"
            " WHERE " + ' AND '.join(filters) +
            " LIMIT 1"
        )
        loan = db.execute(text(loan_sql), params).fetchone()

        if not loan:
            return {"found": False, "message": "I could not find a loan with that number."}

        # Privacy check: verify caller phone matches borrower phone
        loan_phone = _normalize_phone(loan.borrower_phone or "")
        if normalized and loan_phone and normalized[-10:] != loan_phone[-10:]:
            return {
                "found": False,
                "message": "For security, I can only share loan details with the phone number on file. Please contact your loan officer directly.",
            }

        return _format_loan_result(loan)

    # Look up by phone number
    if not normalized:
        return {"found": False, "message": "I need your phone number or loan number to look up your status."}

    params = {"phone_pattern": f"%{normalized[-10:]}%"}
    filters = ["l.borrower_phone LIKE :phone_pattern"]
    if org_id:
        filters.append("l.organization_id = :org_id")
        params["org_id"] = org_id

    # Exclude terminal stages to show the most relevant active loan
    filters.append("l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')")

    active_loan_sql = (
        "SELECT l.id, l.loan_number, l.stage, l.borrower_name, l.borrower_phone,"
        "       l.closing_date, l.loan_officer_name,"
        "       CONCAT(u.first_name, ' ', u.last_name) as lo_name"
        " FROM loans l"
        " LEFT JOIN users u ON u.id = l.loan_officer_id"
        " WHERE " + ' AND '.join(filters) +
        " ORDER BY l.created_at DESC"
        " LIMIT 1"
    )
    loan = db.execute(text(active_loan_sql), params).fetchone()

    if not loan:
        # Try funded loans as fallback
        filters_funded = [
            "l.borrower_phone LIKE :phone_pattern",
            "l.stage = 'FUNDED'",
        ]
        if org_id:
            filters_funded.append("l.organization_id = :org_id")

        funded_loan_sql = (
            "SELECT l.id, l.loan_number, l.stage, l.borrower_name, l.borrower_phone,"
            "       l.closing_date, l.loan_officer_name,"
            "       CONCAT(u.first_name, ' ', u.last_name) as lo_name"
            " FROM loans l"
            " LEFT JOIN users u ON u.id = l.loan_officer_id"
            " WHERE " + ' AND '.join(filters_funded) +
            " ORDER BY l.funded_date DESC"
            " LIMIT 1"
        )
        loan = db.execute(text(funded_loan_sql), params).fetchone()

    if not loan:
        return {"found": False, "message": "I wasn't able to locate a loan with your phone number. Could you provide your loan number?"}

    return _format_loan_result(loan)


def _format_loan_result(loan) -> Dict[str, Any]:
    """Format a loan row into a status result dict."""
    closing_str = None
    if loan.closing_date:
        if hasattr(loan.closing_date, "strftime"):
            closing_str = loan.closing_date.strftime("%B %d, %Y")
        else:
            closing_str = str(loan.closing_date)

    lo_name = loan.lo_name or loan.loan_officer_name or ""

    # Determine next step based on stage
    next_steps = {
        "APPLICATION": "We'll send your initial disclosures shortly.",
        "DISCLOSED": "Please review and sign your disclosures.",
        "PROCESSING": "We may request additional documents from you.",
        "SUBMITTED": "We're waiting for the underwriter's review.",
        "UNDERWRITING": "The underwriter is reviewing your file.",
        "CONDITIONAL_APPROVAL": "Please provide the conditions listed by your loan officer.",
        "APPROVED": "We're preparing to clear you to close.",
        "CLEAR_TO_CLOSE": "Your closing documents will be sent soon.",
        "CTC": "Your closing documents will be sent soon.",
        "DOCS_OUT": "Please review and sign your closing documents.",
    }

    return {
        "found": True,
        "loan": {
            "loan_number": loan.loan_number,
            "stage": loan.stage,
            "borrower_name": loan.borrower_name,
            "lo_name": lo_name.strip() if lo_name else None,
            "closing_date": closing_str,
            "next_step": next_steps.get(loan.stage),
        },
    }


def _default_config() -> Dict[str, Any]:
    """Return default NL IVR configuration with standard mortgage intents."""
    return {
        "greeting": "Thank you for calling. I'm an AI assistant and I can help you with your mortgage questions. How can I help you today?",
        "menu_options": [
            {
                "intent": "loan_status",
                "description": "Check my loan status",
                "action": "lookup_loan",
            },
            {
                "intent": "speak_to_lo",
                "description": "Speak with my loan officer",
                "action": "transfer_lo",
            },
            {
                "intent": "apply",
                "description": "Apply for a mortgage",
                "action": "route_department",
                "department": "sales",
            },
            {
                "intent": "rates",
                "description": "Get rate information",
                "action": "route_department",
                "department": "rates",
            },
            {
                "intent": "callback",
                "description": "Schedule a callback",
                "action": "schedule_callback",
            },
            {
                "intent": "leave_message",
                "description": "Leave a message",
                "action": "take_message",
            },
        ],
        "fallback_action": "take_message",
        "max_retries": 2,
        "language": "en",
    }


def _build_system_prompt(config: Dict[str, Any]) -> str:
    """Build the Vapi assistant system prompt from the IVR config."""
    business = config.get("business_name", "our mortgage company")
    intents = config.get("menu_options", [])

    intent_lines = []
    for opt in intents:
        if isinstance(opt, dict):
            intent_lines.append(f'- "{opt.get("description", opt.get("intent", ""))}" -> call {opt.get("action", "take_message")} function')

    intent_block = "\n".join(intent_lines) if intent_lines else "- Any request -> call take_message function"

    return f"""You are an AI-powered Interactive Voice Response system for {business}. You handle incoming phone calls with natural language understanding.

Your role:
1. Greet callers warmly and determine what they need.
2. Match their request to one of the available intents and call the appropriate function.
3. If you cannot determine their intent after {config.get('max_retries', 2)} attempts, use the take_message function.
4. Always be professional, empathetic, and efficient.
5. Keep responses concise -- callers are on the phone and prefer brief answers.
6. Never share sensitive financial details (SSN, account numbers, income) over the phone.
7. When a function returns a JSON object with an "action": "transfer" field, tell the caller you are transferring them and end your turn.

Available intents and their functions:
{intent_block}

Function usage guidelines:
- "lookup_loan_status": Call when the caller wants to check their loan status. Ask for their name or loan number if needed for verification.
- "schedule_callback": Call when the caller wants someone to call them back. Ask for their name and preferred callback time.
- "transfer_to_lo": Call when the caller wants to speak directly to their loan officer.
- "route_to_department": Call when the caller needs a specific department (sales, processing, rates, support).
- "take_message": Call when no other function matches, or the caller wants to leave a message. Ask for their name and message.

Privacy rules:
- Only share loan status details if the caller's phone number matches the borrower phone on file.
- Never reveal borrower names, addresses, or financial details to unverified callers.
- If verification fails, offer to take a message or schedule a callback.

If the caller says goodbye or has no more questions, politely end the call."""


def _build_vapi_tools() -> List[Dict[str, Any]]:
    """Build the Vapi function tool definitions for the IVR assistant."""
    return [
        {
            "type": "function",
            "function": {
                "name": "route_to_department",
                "description": "Route the caller to a specific department based on their need.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "department": {
                            "type": "string",
                            "description": "Department to route to: sales, processing, rates, support, general",
                            "enum": ["sales", "processing", "rates", "support", "general"],
                        },
                    },
                    "required": ["department"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_loan_status",
                "description": "Look up the caller's loan status by their phone number and optionally their name or loan number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "borrower_name": {
                            "type": "string",
                            "description": "The caller's full name for verification.",
                        },
                        "loan_number": {
                            "type": "string",
                            "description": "The loan number if the caller provides it.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_callback",
                "description": "Schedule a callback from the loan officer to the caller.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "caller_name": {
                            "type": "string",
                            "description": "The caller's name.",
                        },
                        "preferred_time": {
                            "type": "string",
                            "description": "When the caller would like to be called back, e.g. 'tomorrow morning', 'this afternoon', 'ASAP'.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the callback.",
                        },
                    },
                    "required": ["caller_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "transfer_to_lo",
                "description": "Transfer the caller directly to their assigned loan officer.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_message",
                "description": "Record a message from the caller to be delivered to the appropriate team member.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "caller_name": {
                            "type": "string",
                            "description": "The caller's name.",
                        },
                        "message": {
                            "type": "string",
                            "description": "The message the caller wants to leave.",
                        },
                    },
                    "required": ["message"],
                },
            },
        },
    ]


def _log_call_report(payload: Dict, db: Session):
    """Log end-of-call report from Vapi for analytics."""
    try:
        call_data = payload.get("message", {}).get("call", {})
        org_id = _resolve_org_from_payload(payload, db)
        caller_phone = call_data.get("customer", {}).get("number", "")
        duration = payload.get("message", {}).get("durationSeconds", 0)
        transcript = payload.get("message", {}).get("transcript", "")

        db.execute(text("""
            INSERT INTO activities
                (organization_id, type, content, user_metadata, created_at)
            VALUES
                (:org_id, 'Call', :content, :metadata, NOW())
        """), {
            "org_id": org_id,
            "content": f"NL IVR call completed. Caller: {caller_phone}. Duration: {duration}s.",
            "metadata": json.dumps({
                "source": "nl_ivr",
                "caller_phone": caller_phone,
                "duration_seconds": duration,
                "transcript_preview": (transcript or "")[:500],
                "vapi_call_id": call_data.get("id"),
            }),
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log NL IVR call report: {e}")
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass
