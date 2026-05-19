"""
Call Routing Configuration Routes
Manage intelligent call routing based on CRM stages
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
import json
import logging
import os
import httpx

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from middleware.webhook_verification import require_vapi_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/call-routing", tags=["call-routing"])


def get_current_user_flexible():
    """Lazy import auth dependency"""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# ============================================================================
# VAPI ASSISTANT IDS - Configure these for your assistants
# ============================================================================
ASSISTANT_CONFIG = {
    "receptionist": {
        "id": "120e239e-4d19-4e43-ad92-1f8b07d08c8c",  # Aria
        "name": "Aria (Receptionist)",
        "description": "Handles unrecognized callers and general inquiries",
        "stages": []  # Fallback for unknown callers
    },
    "lead": {
        "id": "3e5af9cd-2ba7-4f45-bd93-5320179b2fc4",  # Production Assistant 1
        "name": "Lead Assistant",
        "description": "Handles leads in early stages",
        "stages": ["new", "attempted_contact", "prospect", "application", "pre_qualified", "pre_approved"]
    },
    "active_loan": {
        "id": "08fa09ed-5bb2-4e3a-8c67-26ffb966bc84",  # Production Assistant 2
        "name": "Active Loan Assistant",
        "description": "Handles borrowers with active loans",
        "stages": ["processing", "submitted_to_uw", "approved", "conditional_approval", "clear_to_close", "docs_out", "docs_back"]
    },
    "mum": {
        "id": "faf78118-6808-4742-b63e-af8f7affd3cd",  # MUM Concierge
        "name": "MUM Concierge",
        "description": "Handles past clients in MUM program",
        "stages": ["active", "paid_off", "refinance_opportunity"]
    }
}

PHONE_NUMBER_ID = "6adaf897-34d7-42d5-bc34-f1a17162a453"
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AssistantConfigUpdate(BaseModel):
    """Update assistant configuration"""
    assistant_type: str  # receptionist, lead, active_loan, mum
    vapi_assistant_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[str]] = None
    is_enabled: bool = True


class RoutingConfig(BaseModel):
    """Full routing configuration"""
    receptionist_id: str
    lead_assistant_id: str
    active_loan_assistant_id: str
    mum_assistant_id: str
    routing_enabled: bool = True


class CallerLookupResult(BaseModel):
    """Result of caller lookup"""
    found: bool
    caller_type: str  # unknown, lead, active_loan, mum
    caller_name: Optional[str] = None
    stage: Optional[str] = None
    assistant_id: str
    assistant_name: str
    context: Optional[Dict[str, Any]] = None


_routing_table_ensured = False


def _ensure_routing_table(db: Session):
    global _routing_table_ensured
    if _routing_table_ensured:
        return
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS call_routing_logs (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(20),
                caller_type VARCHAR(50),
                caller_name VARCHAR(255),
                stage VARCHAR(100),
                assistant_id VARCHAR(255),
                assistant_name VARCHAR(255),
                organization_id INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        _routing_table_ensured = True
    except Exception as e:
        logger.debug("Routing table ensure failed (non-fatal): %s", e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


# ============================================================================
# CALLER LOOKUP - Core routing logic
# ============================================================================

def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only"""
    if not phone:
        return ""
    return ''.join(filter(str.isdigit, phone))[-10:]  # Get last 10 digits


def lookup_caller_in_crm(db: Session, phone: str, org_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Look up caller in CRM database across leads, loans, and MUM clients.
    Returns caller type and appropriate assistant.

    org_id is optional: when provided (e.g. from authenticated endpoints), queries
    are scoped to that organization. When omitted (e.g. from Vapi webhook), all
    organizations are searched.
    """
    phone_clean = normalize_phone(phone)

    if not phone_clean or len(phone_clean) < 10:
        return {
            "found": False,
            "caller_type": "unknown",
            "assistant_id": ASSISTANT_CONFIG["receptionist"]["id"],
            "assistant_name": ASSISTANT_CONFIG["receptionist"]["name"]
        }

    org_filter = "AND organization_id = :org_id" if org_id else ""
    params: Dict[str, Any] = {"phone_pattern": f"%{phone_clean}"}
    if org_id:
        params["org_id"] = org_id

    # 1. Check MUM clients first (highest priority - past clients)
    try:
        mum_query = """
            SELECT id, first_name, last_name, phone, status, loan_id
            FROM mum_clients
            WHERE phone LIKE :phone_pattern
            AND status IN ('active', 'paid_off', 'refinance_opportunity')
            """ + org_filter + """
            LIMIT 1
        """
        mum_result = db.execute(text(mum_query), params).fetchone()

        if mum_result:
            return {
                "found": True,
                "caller_type": "mum",
                "caller_name": f"{mum_result.first_name} {mum_result.last_name}".strip(),
                "stage": mum_result.status,
                "assistant_id": ASSISTANT_CONFIG["mum"]["id"],
                "assistant_name": ASSISTANT_CONFIG["mum"]["name"],
                "context": {
                    "mum_client_id": mum_result.id,
                    "loan_id": mum_result.loan_id
                }
            }
    except Exception as e:
        logger.warning(f"MUM lookup failed: {e}")

    # 2. Check active loans
    try:
        loan_org_filter = org_filter.replace('organization_id', 'l.organization_id')
        loan_query = """
            SELECT l.id, l.borrower_name, l.borrower_phone, l.stage, l.loan_number,
                   l.expected_close_date, l.property_address
            FROM loans l
            WHERE (l.borrower_phone LIKE :phone_pattern OR l.coborrower_phone LIKE :phone_pattern)
            AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'withdrawn')
            """ + loan_org_filter + """
            ORDER BY l.created_at DESC
            LIMIT 1
        """
        loan_result = db.execute(text(loan_query), params).fetchone()

        if loan_result:
            return {
                "found": True,
                "caller_type": "active_loan",
                "caller_name": loan_result.borrower_name,
                "stage": loan_result.stage,
                "assistant_id": ASSISTANT_CONFIG["active_loan"]["id"],
                "assistant_name": ASSISTANT_CONFIG["active_loan"]["name"],
                "context": {
                    "loan_id": loan_result.id,
                    "loan_number": loan_result.loan_number,
                    "expected_close": str(loan_result.expected_close_date) if loan_result.expected_close_date else None,
                    "property": loan_result.property_address
                }
            }
    except Exception as e:
        logger.warning(f"Loan lookup failed: {e}")

    # 3. Check leads
    try:
        lead_query = """
            SELECT id, first_name, last_name, name, phone, stage, loan_type, preapproval_amount
            FROM leads
            WHERE phone LIKE :phone_pattern
            AND stage NOT IN ('withdrawn', 'does_not_qualify', 'converted')
            """ + org_filter + """
            ORDER BY created_at DESC
            LIMIT 1
        """
        lead_result = db.execute(text(lead_query), params).fetchone()

        if lead_result:
            caller_name = lead_result.name or f"{lead_result.first_name or ''} {lead_result.last_name or ''}".strip()
            return {
                "found": True,
                "caller_type": "lead",
                "caller_name": caller_name,
                "stage": lead_result.stage,
                "assistant_id": ASSISTANT_CONFIG["lead"]["id"],
                "assistant_name": ASSISTANT_CONFIG["lead"]["name"],
                "context": {
                    "lead_id": lead_result.id,
                    "loan_type": lead_result.loan_type,
                    "preapproval_amount": float(lead_result.preapproval_amount) if lead_result.preapproval_amount else None
                }
            }
    except Exception as e:
        logger.warning(f"Lead lookup failed: {e}")

    # 4. No match found - route to receptionist
    return {
        "found": False,
        "caller_type": "unknown",
        "assistant_id": ASSISTANT_CONFIG["receptionist"]["id"],
        "assistant_name": ASSISTANT_CONFIG["receptionist"]["name"]
    }


# ============================================================================
# VAPI WEBHOOK FOR INTELLIGENT ROUTING
# ============================================================================

@router.post("/webhook/route-call")
async def route_inbound_call(
    request: Request,
    raw_body: bytes = Depends(require_vapi_webhook),
    db: Session = Depends(get_db),
):
    """
    Vapi webhook endpoint for intelligent call routing.
    Called when a call comes in to determine which assistant to use.

    Configure your Vapi phone number to use this URL:
    https://your-domain.com/api/v1/call-routing/webhook/route-call

    Signature verification is handled by the require_vapi_webhook dependency.
    """
    try:
        payload = json.loads(raw_body)
        message = payload.get("message", {})
        message_type = message.get("type")

        logger.info(f"Call routing webhook: type={message_type}")

        # Handle assistant-request type
        if message_type == "assistant-request":
            call_data = message.get("call", {})
            customer = call_data.get("customer", {})
            phone_number = customer.get("number") or call_data.get("phoneNumber")

            logger.info(f"Routing call from: {phone_number}")

            # Look up caller in CRM
            result = lookup_caller_in_crm(db, phone_number)

            logger.info(f"Routing decision: {result['caller_type']} -> {result['assistant_name']}")

            # Log the routing decision (ensure table exists on first call)
            _ensure_routing_table(db)
            try:
                db.execute(text("""
                    INSERT INTO call_routing_logs
                    (phone_number, caller_type, caller_name, stage, assistant_id, assistant_name, organization_id, created_at)
                    VALUES (:phone, :caller_type, :caller_name, :stage, :assistant_id, :assistant_name, :organization_id, :created_at)
                """), {
                    "phone": phone_number,
                    "caller_type": result["caller_type"],
                    "caller_name": result.get("caller_name"),
                    "stage": result.get("stage"),
                    "assistant_id": result["assistant_id"],
                    "assistant_name": result["assistant_name"],
                    "organization_id": result.get("context", {}).get("organization_id"),
                    "created_at": datetime.now(timezone.utc)
                })
                db.commit()
            except Exception as log_err:
                logger.warning(f"Failed to log routing: {log_err}")
                try:
                    db.rollback()
                except Exception as _exc:  # noqa: BLE001
                    pass

            caller_name = result.get("caller_name", "")
            caller_type = result["caller_type"]

            context_lines = []
            if caller_name:
                context_lines.append(f"The caller is {caller_name}.")
            if result.get("stage"):
                context_lines.append(f"Their current stage is: {result['stage']}.")
            ctx = result.get("context", {})
            if ctx.get("loan_number"):
                context_lines.append(f"Loan number: {ctx['loan_number']}.")
            if ctx.get("property"):
                context_lines.append(f"Property: {ctx['property']}.")
            caller_context = " ".join(context_lines)

            system_prompt = (
                "You are Aria, an AI assistant for The Tim Loss Team at CMG Home Loans. "
                "You're a mortgage loan officer's virtual receptionist.\n\n"
            )
            if caller_type == "mum":
                system_prompt += (
                    "This caller is a past client in the MUM (Mortgage Update Monthly) program. "
                    "Be warm and familiar. Ask how you can help — refinance questions, rate checks, referrals.\n"
                )
            elif caller_type == "active_loan":
                system_prompt += (
                    "This caller has an active loan in process. "
                    "They may be calling about loan status, document requests, or closing timeline.\n"
                )
            elif caller_type == "lead":
                system_prompt += (
                    "This caller is a lead/prospect. "
                    "Be helpful and professional. Answer general mortgage questions.\n"
                )
            else:
                system_prompt += (
                    "This is an unknown/new caller. Be welcoming and professional.\n"
                )

            if caller_context:
                system_prompt += f"\nCaller info: {caller_context}\n"

            system_prompt += (
                "\nRules:\n"
                "- Never provide specific rate quotes or fees\n"
                "- Never give legal or tax advice\n"
                "- Be concise — this is a phone call\n"
                "- Offer to schedule a callback or take a message\n"
                "- Always confirm the caller's name and best callback number before ending"
            )

            first_msg = f"Hi{', ' + caller_name.split()[0] if caller_name else ''}! This is Aria with The Tim Loss Team. How can I help you today?"

            return {
                "assistant": {
                    "name": f"Aria - {result['assistant_name']}",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "messages": [{"role": "system", "content": system_prompt}],
                    },
                    "voice": {"provider": "deepgram", "voiceId": "asteria"},
                    "firstMessage": first_msg,
                    "silenceTimeoutSeconds": 30,
                    "maxDurationSeconds": 600,
                }
            }

        # For other message types, just acknowledge
        return {"status": "received"}

    except SQLAlchemyError as e:
        logger.error(f"Call routing error: {e}")
        return {
            "assistant": {
                "name": "Aria - Fallback",
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "messages": [{"role": "system", "content": (
                        "You are Aria, an AI assistant for The Tim Loss Team. "
                        "Greet the caller, offer to take a message or schedule a callback. "
                        "Be concise — this is a phone call."
                    )}],
                },
                "voice": {"provider": "deepgram", "voiceId": "asteria"},
                "firstMessage": "Hi, this is Aria with The Tim Loss Team. How can I help you today?",
                "silenceTimeoutSeconds": 30,
                "maxDurationSeconds": 300,
            }
        }


# ============================================================================
# CONFIGURATION ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_routing_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get current call routing configuration"""
    return {
        "assistants": ASSISTANT_CONFIG,
        "phone_number_id": PHONE_NUMBER_ID,
        "webhook_url": f"{os.getenv('API_URL') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'https://api.perenniaai.com'}/api/v1/call-routing/webhook/route-call",
        "routing_enabled": True
    }


@router.get("/test-lookup")
async def test_caller_lookup(
    phone: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Test the caller lookup for a given phone number"""
    org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
    result = lookup_caller_in_crm(db, phone, org_id=org_id)
    return {
        "phone_searched": phone,
        "phone_normalized": normalize_phone(phone),
        "result": result
    }


@router.get("/assistants")
async def list_assistants(
    current_user = Depends(get_current_user_flexible)
):
    """List all configured assistants"""
    return {
        "assistants": [
            {
                "type": key,
                "id": config["id"],
                "name": config["name"],
                "description": config["description"],
                "stages": config.get("stages", [])
            }
            for key, config in ASSISTANT_CONFIG.items()
        ]
    }


@router.get("/logs")
async def get_routing_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get recent call routing logs"""
    try:
        org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
        logs = db.execute(text("""
            SELECT id, phone_number, caller_type, caller_name, stage,
                   assistant_id, assistant_name, created_at
            FROM call_routing_logs
            WHERE organization_id = :org_id
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit, "org_id": org_id}).fetchall()

        return {
            "logs": [
                {
                    "id": log.id,
                    "phone": log.phone_number,
                    "caller_type": log.caller_type,
                    "caller_name": log.caller_name,
                    "stage": log.stage,
                    "assistant_name": log.assistant_name,
                    "created_at": log.created_at.isoformat() if log.created_at else None
                }
                for log in logs
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return {"logs": [], "error": "Internal server error"}


@router.post("/configure-phone")
async def configure_phone_routing(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Configure the Vapi phone number to use intelligent routing.
    This sets the serverUrl on the phone number to point to our routing webhook.
    """
    domain = (
        os.getenv("API_URL")
        or os.getenv("PRODUCTION_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or "https://api.perenniaai.com"
    )
    if domain and not domain.startswith("http"):
        domain = f"https://{domain}"
    webhook_url = f"{domain}/api/v1/call-routing/webhook/route-call"

    try:
        async with httpx.AsyncClient() as client:
            # Update phone number to use our routing webhook
            response = await client.patch(
                f"https://api.vapi.ai/phone-number/{PHONE_NUMBER_ID}",
                headers={
                    "Authorization": f"Bearer {VAPI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "server": {"url": webhook_url},
                    "assistantId": None,
                    "squadId": None,
                },
                timeout=15
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Phone number configured for intelligent routing",
                    "webhook_url": webhook_url,
                    "phone_number_id": PHONE_NUMBER_ID
                }
            else:
                return {
                    "success": False,
                    "error": f"Vapi API error: {response.status_code}",
                    "response": response.text
                }

    except Exception as e:
        logger.error(f"Phone configuration error: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/migrate")
async def run_routing_migration(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create call routing logs table"""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS call_routing_logs (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(20),
                caller_type VARCHAR(50),
                caller_name VARCHAR(255),
                stage VARCHAR(100),
                assistant_id VARCHAR(255),
                assistant_name VARCHAR(255),
                organization_id INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Add organization_id column if table already exists without it
        db.execute(text("""
            ALTER TABLE call_routing_logs
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_routing_logs_created
            ON call_routing_logs(created_at DESC)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_routing_logs_phone
            ON call_routing_logs(phone_number)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_routing_logs_org
            ON call_routing_logs(organization_id)
        """))

        db.commit()

        return {"success": True, "message": "Migration completed"}

    except SQLAlchemyError as e:
        logger.error(f"Migration error: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/status")
async def get_routing_status(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get routing system status and stats"""
    try:
        org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
        # Get today's stats
        stats = db.execute(text("""
            SELECT
                caller_type,
                COUNT(*) as count
            FROM call_routing_logs
            WHERE created_at >= CURRENT_DATE
            AND organization_id = :org_id
            GROUP BY caller_type
        """), {"org_id": org_id}).fetchall()

        stats_dict = {row.caller_type: row.count for row in stats}

        # Check if phone is configured correctly
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.vapi.ai/phone-number/{PHONE_NUMBER_ID}",
                headers={
                    "Authorization": f"Bearer {VAPI_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )

            phone_config = response.json() if response.status_code == 200 else {}

        return {
            "status": "active",
            "today_stats": {
                "leads": stats_dict.get("lead", 0),
                "active_loans": stats_dict.get("active_loan", 0),
                "mum_clients": stats_dict.get("mum", 0),
                "unknown": stats_dict.get("unknown", 0),
                "total": sum(stats_dict.values())
            },
            "phone_config": {
                "number": phone_config.get("number"),
                "has_server_url": bool(phone_config.get("serverUrl")),
                "server_url": phone_config.get("serverUrl"),
                "assistant_id": phone_config.get("assistantId")
            },
            "assistants_configured": len(ASSISTANT_CONFIG)
        }

    except Exception as e:
        logger.error(f"Status check error: {e}")
        return {"status": "error", "error": "Internal server error"}


# ============================================================================
# DIAGNOSTICS — Check and fix Vapi phone number config
# ============================================================================

@router.get("/diagnose")
async def diagnose_call_routing():
    """
    Check Vapi phone number configuration and report issues.
    No auth required — returns only diagnostic info, no secrets.
    """
    issues = []
    config_info = {}

    api_domain = (
        os.getenv("API_URL")
        or os.getenv("PRODUCTION_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or "https://api.perenniaai.com"
    )
    if api_domain and not api_domain.startswith("http"):
        api_domain = f"https://{api_domain}"

    expected_webhook = f"{api_domain}/api/v1/call-routing/webhook/route-call"
    config_info["expected_webhook_url"] = expected_webhook
    config_info["phone_number_id"] = PHONE_NUMBER_ID

    if not VAPI_API_KEY:
        issues.append({
            "severity": "CRITICAL",
            "issue": "VAPI_API_KEY not set",
            "fix": "Set VAPI_API_KEY env var in Railway",
        })
        return {"issues": issues, "config": config_info, "phone_config": None}

    config_info["vapi_api_key_set"] = True

    webhook_secret = os.getenv("VAPI_WEBHOOK_SECRET", "")
    env_name = os.getenv("RAILWAY_ENVIRONMENT", "development")
    config_info["environment"] = env_name
    config_info["webhook_secret_set"] = bool(webhook_secret)

    if not webhook_secret and env_name in ("production", "staging"):
        issues.append({
            "severity": "CRITICAL",
            "issue": f"VAPI_WEBHOOK_SECRET not set in {env_name} — webhooks rejected with 503",
            "fix": "Set VAPI_WEBHOOK_SECRET env var in Railway, then reconfigure phone",
        })

    phone_config = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.vapi.ai/phone-number/{PHONE_NUMBER_ID}",
                headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            )
            if resp.status_code == 200:
                phone_config = resp.json()
            else:
                issues.append({
                    "severity": "CRITICAL",
                    "issue": f"Vapi phone number lookup failed: HTTP {resp.status_code}",
                    "fix": "Check PHONE_NUMBER_ID and VAPI_API_KEY",
                    "detail": resp.text[:300],
                })
    except Exception as e:
        issues.append({
            "severity": "CRITICAL",
            "issue": f"Cannot reach Vapi API: {e}",
            "fix": "Check network connectivity and VAPI_API_KEY",
        })

    if phone_config:
        current_server_url = phone_config.get("serverUrl") or (phone_config.get("server") or {}).get("url")
        current_assistant_id = phone_config.get("assistantId")
        phone_number = phone_config.get("number")

        config_info["phone_number"] = phone_number
        config_info["current_server_url"] = current_server_url
        config_info["current_assistant_id"] = current_assistant_id

        if not current_server_url and not current_assistant_id:
            issues.append({
                "severity": "CRITICAL",
                "issue": "Phone number has NO serverUrl AND NO assistantId — calls get 'application error'",
                "fix": "POST to /api/v1/call-routing/configure-phone to set serverUrl",
            })
        elif current_server_url and current_server_url != expected_webhook:
            issues.append({
                "severity": "HIGH",
                "issue": f"serverUrl mismatch: '{current_server_url}' vs expected '{expected_webhook}'",
                "fix": "POST to /api/v1/call-routing/configure-phone to update",
            })
        elif not current_server_url and current_assistant_id:
            issues.append({
                "severity": "INFO",
                "issue": f"Phone uses direct assistantId ({current_assistant_id}) — not dynamic routing",
                "fix": "If dynamic routing desired, POST to /api/v1/call-routing/configure-phone",
            })

        for name, cfg in ASSISTANT_CONFIG.items():
            aid = cfg["id"]
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://api.vapi.ai/assistant/{aid}",
                        headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
                    )
                    if resp.status_code != 200:
                        issues.append({
                            "severity": "HIGH",
                            "issue": f"Assistant '{name}' ({aid}) not found in Vapi (HTTP {resp.status_code})",
                            "fix": f"Update ASSISTANT_CONFIG['{name}']['id'] with a valid Vapi assistant ID",
                        })
            except Exception as _exc:  # noqa: BLE001
                pass

    if not issues:
        issues.append({"severity": "OK", "issue": "All checks passed"})

    return {"issues": issues, "config": config_info, "phone_config": phone_config}


@router.post("/fix-phone-config")
async def fix_phone_config():
    """
    One-shot fix: configure the Vapi phone number with the correct serverUrl.
    No auth required (idempotent, only sets the webhook URL).
    """
    if not VAPI_API_KEY:
        return {"success": False, "error": "VAPI_API_KEY not set"}

    domain = (
        os.getenv("API_URL")
        or os.getenv("PRODUCTION_DOMAIN")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or "https://api.perenniaai.com"
    )
    if domain and not domain.startswith("http"):
        domain = f"https://{domain}"

    webhook_url = f"{domain}/api/v1/call-routing/webhook/route-call"
    webhook_secret = os.getenv("VAPI_WEBHOOK_SECRET", "")

    server_config: Dict[str, Any] = {"url": webhook_url}
    if webhook_secret:
        server_config["secret"] = webhook_secret
    patch_payload: Dict[str, Any] = {
        "server": server_config,
        "assistantId": None,
        "squadId": None,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                f"https://api.vapi.ai/phone-number/{PHONE_NUMBER_ID}",
                headers={
                    "Authorization": f"Bearer {VAPI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=patch_payload,
            )
            if resp.status_code == 200:
                return {
                    "success": True,
                    "webhook_url": webhook_url,
                    "secret_included": bool(webhook_secret),
                    "phone_number_id": PHONE_NUMBER_ID,
                }
            else:
                return {
                    "success": False,
                    "error": f"Vapi API: HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }
    except Exception as e:
        return {"success": False, "error": str(e)}
