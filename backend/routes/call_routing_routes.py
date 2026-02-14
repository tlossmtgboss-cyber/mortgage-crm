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
import logging
import os
import httpx

import hmac

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")

router = APIRouter(prefix="/api/v1/call-routing", tags=["call-routing"])


def get_current_user_flexible():
    """Lazy import auth dependency"""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# ============================================================================
# VAPI ASSISTANT IDS - Configure these for your assistants
# ============================================================================
ASSISTANT_CONFIG = {
    "receptionist": {
        "id": "120e239e-4d19-4e43-ad92-1f8b07d08c8c",  # Sam
        "name": "Sam (Receptionist)",
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
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "13af9bfd-8639-4a4a-90d9-fe5fdd8ec886")


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


# ============================================================================
# CALLER LOOKUP - Core routing logic
# ============================================================================

def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only"""
    if not phone:
        return ""
    return ''.join(filter(str.isdigit, phone))[-10:]  # Get last 10 digits


def lookup_caller_in_crm(db: Session, phone: str) -> Dict[str, Any]:
    """
    Look up caller in CRM database across leads, loans, and MUM clients.
    Returns caller type and appropriate assistant.
    """
    phone_clean = normalize_phone(phone)

    if not phone_clean or len(phone_clean) < 10:
        return {
            "found": False,
            "caller_type": "unknown",
            "assistant_id": ASSISTANT_CONFIG["receptionist"]["id"],
            "assistant_name": ASSISTANT_CONFIG["receptionist"]["name"]
        }

    # 1. Check MUM clients first (highest priority - past clients)
    try:
        mum_result = db.execute(text("""
            SELECT id, first_name, last_name, phone, status, loan_id
            FROM mum_clients
            WHERE phone LIKE :phone_pattern
            AND status IN ('active', 'paid_off', 'refinance_opportunity')
            LIMIT 1
        """), {"phone_pattern": f"%{phone_clean}"}).fetchone()

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
        loan_result = db.execute(text("""
            SELECT l.id, l.borrower_name, l.borrower_phone, l.stage, l.loan_number,
                   l.expected_close_date, l.property_address
            FROM loans l
            WHERE (l.borrower_phone LIKE :phone_pattern OR l.coborrower_phone LIKE :phone_pattern)
            AND l.stage NOT IN ('funded', 'cancelled', 'denied', 'withdrawn')
            ORDER BY l.created_at DESC
            LIMIT 1
        """), {"phone_pattern": f"%{phone_clean}"}).fetchone()

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
        lead_result = db.execute(text("""
            SELECT id, first_name, last_name, name, phone, stage, loan_type, preapproval_amount
            FROM leads
            WHERE phone LIKE :phone_pattern
            AND stage NOT IN ('withdrawn', 'does_not_qualify', 'converted')
            ORDER BY created_at DESC
            LIMIT 1
        """), {"phone_pattern": f"%{phone_clean}"}).fetchone()

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
    db: Session = Depends(get_db)
):
    """
    Vapi webhook endpoint for intelligent call routing.
    Called when a call comes in to determine which assistant to use.

    Configure your Vapi phone number to use this URL:
    https://your-domain.com/api/v1/call-routing/webhook/route-call
    """
    # Validate Vapi webhook secret — fail closed if not configured
    if not VAPI_WEBHOOK_SECRET:
        logger.error("VAPI_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    vapi_secret = request.headers.get("X-Vapi-Secret", "")
    if not hmac.compare_digest(vapi_secret, VAPI_WEBHOOK_SECRET):
        logger.warning(f"Invalid Vapi secret on route-call webhook from {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid webhook authentication")

    try:
        payload = await request.json()
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

            # Log the routing decision
            try:
                db.execute(text("""
                    INSERT INTO call_routing_logs
                    (phone_number, caller_type, caller_name, stage, assistant_id, assistant_name, created_at)
                    VALUES (:phone, :caller_type, :caller_name, :stage, :assistant_id, :assistant_name, :created_at)
                """), {
                    "phone": phone_number,
                    "caller_type": result["caller_type"],
                    "caller_name": result.get("caller_name"),
                    "stage": result.get("stage"),
                    "assistant_id": result["assistant_id"],
                    "assistant_name": result["assistant_name"],
                    "created_at": datetime.now(timezone.utc)
                })
                db.commit()
            except Exception as log_err:
                logger.warning(f"Failed to log routing: {log_err}")

            # Return the assistant to use
            return {
                "assistantId": result["assistant_id"]
            }

        # For other message types, just acknowledge
        return {"status": "received"}

    except SQLAlchemyError as e:
        logger.error(f"Call routing error: {e}")
        # Default to receptionist on error
        return {
            "assistantId": ASSISTANT_CONFIG["receptionist"]["id"]
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
        "webhook_url": f"{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://app.perenniaai.com')}/api/v1/call-routing/webhook/route-call",
        "routing_enabled": True
    }


@router.get("/test-lookup")
async def test_caller_lookup(
    phone: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Test the caller lookup for a given phone number"""
    result = lookup_caller_in_crm(db, phone)
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
        logs = db.execute(text("""
            SELECT id, phone_number, caller_type, caller_name, stage,
                   assistant_id, assistant_name, created_at
            FROM call_routing_logs
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

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
    webhook_url = f"{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'https://app.perenniaai.com')}/api/v1/call-routing/webhook/route-call"

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
                    "serverUrl": webhook_url,
                    "assistantId": None  # Remove direct assistant - use serverUrl routing
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
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_routing_logs_created
            ON call_routing_logs(created_at DESC)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_routing_logs_phone
            ON call_routing_logs(phone_number)
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
        # Get today's stats
        stats = db.execute(text("""
            SELECT
                caller_type,
                COUNT(*) as count
            FROM call_routing_logs
            WHERE created_at >= CURRENT_DATE
            GROUP BY caller_type
        """)).fetchall()

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
