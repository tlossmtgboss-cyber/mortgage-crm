"""
Telnyx-Retell Bridge Routes

API endpoints for connecting Telnyx phone numbers with Retell AI voice agents.
"""

import os
import logging
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from integrations.telnyx_retell_bridge import TelnyxRetellBridge, get_bridge_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telnyx-retell", tags=["Telnyx-Retell Bridge"])

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


def get_db():
    """Get database session."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    return _get_db()


def get_current_user():
    """Get current user."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    return _get_current_user()


# ==================== Request/Response Models ====================

class ConnectNumberRequest(BaseModel):
    """Request to connect a Telnyx number to Retell."""
    phone_number: str = Field(..., description="Telnyx phone number in E.164 format")
    retell_agent_id: str = Field(..., description="Retell agent ID to handle calls")
    connection_name: Optional[str] = Field(None, description="Name for the SIP connection")


class ConnectNumberResponse(BaseModel):
    """Response from connecting a number."""
    success: bool
    phone_number: str
    retell_agent_id: str
    configuration: dict
    next_steps: List[str]
    message: str


class TelnyxNumberInfo(BaseModel):
    """Information about a Telnyx phone number."""
    phone_number: str
    connection_id: Optional[str]
    connection_name: Optional[str]
    status: str
    is_connected_to_retell: bool


class GenerateTeXMLRequest(BaseModel):
    """Request to generate TeXML for Retell forwarding."""
    retell_agent_id: str


# ==================== Helper Functions ====================

def get_user_telnyx_key(db: Session, user_id: int) -> Optional[str]:
    """Get user's Telnyx API key from database."""
    result = db.execute(
        text("""
        SELECT telnyx_api_key FROM user_twilio_config  -- Legacy table name
        WHERE user_id = :user_id
        """),
        {"user_id": user_id}
    ).fetchone()

    if result and result[0]:
        return result[0]

    # Fall back to environment variable
    return os.getenv("TELNYX_API_KEY")


def get_user_retell_key(db: Session, user_id: int) -> Optional[str]:
    """Get user's Retell API key from database."""
    result = db.execute(
        text("""
        SELECT retell_api_key FROM user_retell_config
        WHERE user_id = :user_id
        """),
        {"user_id": user_id}
    ).fetchone()

    if result and result[0]:
        return result[0]

    return os.getenv("RETELL_API_KEY")


def get_bridge(db: Session, user_id: int) -> TelnyxRetellBridge:
    """Get configured bridge for user."""
    telnyx_key = get_user_telnyx_key(db, user_id)
    retell_key = get_user_retell_key(db, user_id)

    if not telnyx_key:
        raise HTTPException(
            status_code=400,
            detail="Telnyx API key not configured. Go to Settings > Integrations to add your Telnyx credentials."
        )

    if not retell_key:
        raise HTTPException(
            status_code=400,
            detail="Retell AI API key not configured. Go to Settings > Integrations to add your Retell credentials."
        )

    try:
        return get_bridge_for_user(telnyx_key, retell_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Status Endpoint ====================

@router.get("/status")
async def get_bridge_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if both Telnyx and Retell are configured for the user."""
    user_id = current_user.get("id") or current_user.get("user_id")

    telnyx_configured = get_user_telnyx_key(db, user_id) is not None
    retell_configured = get_user_retell_key(db, user_id) is not None

    # Check for existing connections
    connections = []
    if telnyx_configured and retell_configured:
        result = db.execute(
            text("""
            SELECT phone_number, retell_agent_id, created_at
            FROM retell_phone_numbers
            WHERE user_id = :user_id AND imported = TRUE
            """),
            {"user_id": user_id}
        ).fetchall()
        connections = [
            {
                "phone_number": row[0],
                "retell_agent_id": row[1],
                "connected_at": row[2].isoformat() if row[2] else None,
            }
            for row in result
        ]

    return {
        "telnyx_configured": telnyx_configured,
        "retell_configured": retell_configured,
        "bridge_ready": telnyx_configured and retell_configured,
        "connected_numbers": len(connections),
        "connections": connections,
    }


# ==================== Phone Number Endpoints ====================

@router.get("/telnyx-numbers")
async def list_telnyx_numbers(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List available Telnyx phone numbers that can be connected to Retell."""
    user_id = current_user.get("id") or current_user.get("user_id")
    bridge = get_bridge(db, user_id)

    try:
        numbers = await bridge.list_telnyx_numbers()

        # Check which numbers are already connected to Retell
        connected_result = db.execute(
            text("""
            SELECT phone_number FROM retell_phone_numbers
            WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchall()
        connected_numbers = {row[0] for row in connected_result}

        formatted_numbers = []
        for num in numbers:
            phone = num.get("phone_number")
            formatted_numbers.append({
                "phone_number": phone,
                "id": num.get("id"),
                "connection_id": num.get("connection_id"),
                "connection_name": num.get("connection_name"),
                "status": num.get("status"),
                "is_connected_to_retell": phone in connected_numbers,
                "purchased_at": num.get("purchased_at"),
            })

        return {
            "phone_numbers": formatted_numbers,
            "total": len(formatted_numbers),
            "connected_count": len([n for n in formatted_numbers if n["is_connected_to_retell"]]),
        }

    except Exception as e:
        logger.error(f"Failed to list Telnyx numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/connect")
async def connect_number_to_retell(
    request: ConnectNumberRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect a Telnyx phone number to a Retell AI agent.

    This will:
    1. Create SIP credentials on Telnyx for Retell
    2. Import the phone number into Retell
    3. Return configuration for forwarding inbound calls
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    bridge = get_bridge(db, user_id)

    try:
        # Run the setup workflow
        result = await bridge.setup_telnyx_retell_connection(
            phone_number=request.phone_number,
            retell_agent_id=request.retell_agent_id,
            connection_name=request.connection_name or f"Retell-{request.phone_number}",
        )

        if result.get("success"):
            # Store the connection in database
            db.execute(
                text("""
                INSERT INTO retell_phone_numbers (
                    user_id, phone_number, retell_agent_id, imported, created_at
                ) VALUES (
                    :user_id, :phone_number, :agent_id, TRUE, :created_at
                )
                ON CONFLICT (phone_number) DO UPDATE SET
                    retell_agent_id = :agent_id,
                    imported = TRUE
                """),
                {
                    "user_id": user_id,
                    "phone_number": request.phone_number,
                    "agent_id": request.retell_agent_id,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            db.commit()

        return result

    except Exception as e:
        logger.error(f"Failed to connect number to Retell: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/disconnect/{phone_number}")
async def disconnect_number(
    phone_number: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect a phone number from Retell.

    Note: This removes the number from Retell but keeps it in Telnyx.
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    bridge = get_bridge(db, user_id)

    try:
        # Remove from local database
        db.execute(
            text("""
            DELETE FROM retell_phone_numbers
            WHERE user_id = :user_id AND phone_number = :phone_number
            """),
            {"user_id": user_id, "phone_number": phone_number}
        )
        db.commit()

        # Note: We don't delete from Retell API here as that might
        # require different handling. The user can do that in Retell dashboard.

        return {
            "success": True,
            "message": f"Disconnected {phone_number} from Retell tracking. "
                       f"You may also need to remove it from Retell dashboard.",
        }

    except Exception as e:
        logger.error(f"Failed to disconnect number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== TeXML Generation ====================

@router.post("/generate-texml")
async def generate_texml_for_retell(
    request: GenerateTeXMLRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate TeXML code for forwarding Telnyx calls to Retell.

    Use this TeXML as the response from your Telnyx voice webhook
    to forward incoming calls to Retell AI.
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    bridge = get_bridge(db, user_id)

    texml = bridge.generate_texml_for_retell(request.retell_agent_id)

    return {
        "texml": texml,
        "retell_agent_id": request.retell_agent_id,
        "instructions": [
            "1. Set up a TeXML application in Telnyx",
            "2. Point the voice webhook to your server",
            "3. Return this TeXML when calls come in",
            "4. Or paste this directly in Telnyx's static TeXML",
        ],
    }


# ==================== Webhook Handler ====================

@router.post("/webhook/inbound")
async def handle_inbound_call(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for Telnyx inbound calls.

    When configured as the voice URL for a Telnyx number,
    this will return TeXML to forward the call to the appropriate Retell agent.
    """
    # Verify Telnyx webhook signature
    telnyx_public_key = os.getenv("TELNYX_PUBLIC_KEY")
    if not telnyx_public_key:
        logger.error("TELNYX_PUBLIC_KEY not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook verification not configured")
    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp = request.headers.get("telnyx-timestamp", "")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    try:
        from telephony.providers.telnyx.webhooks import validate_telnyx_webhook
        raw_body = await request.body()
        if not validate_telnyx_webhook(raw_body, signature, timestamp, telnyx_public_key):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    except HTTPException:
        raise
    except ImportError:
        logger.error("Telnyx webhook validation module not available")
        raise HTTPException(status_code=500, detail="Webhook verification unavailable")
    except Exception as e:
        logger.error(f"Telnyx signature validation error: {e}")
        raise HTTPException(status_code=401, detail="Webhook signature validation failed")

    try:
        body = await request.json()

        # Extract call details
        call_control_id = body.get("data", {}).get("payload", {}).get("call_control_id")
        from_number = body.get("data", {}).get("payload", {}).get("from")
        to_number = body.get("data", {}).get("payload", {}).get("to")

        logger.info(f"Inbound call: {from_number} -> {to_number}")

        # Look up which Retell agent handles this number
        result = db.execute(
            text("""
            SELECT retell_agent_id FROM retell_phone_numbers
            WHERE phone_number = :phone_number AND imported = TRUE
            """),
            {"phone_number": to_number}
        ).fetchone()

        if not result:
            # No agent configured, return busy
            return Response(
                content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, this number is not configured. Goodbye.</Say>
    <Hangup/>
</Response>""",
                media_type="application/xml",
            )

        retell_agent_id = result[0]

        # Generate TeXML to forward to Retell
        retell_sip = f"sip:{retell_agent_id}@inbound.retellai.com"

        texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>{retell_sip}</Sip>
    </Dial>
</Response>"""

        logger.info(f"Forwarding call to Retell agent: {retell_agent_id}")

        return Response(content=texml, media_type="application/xml")

    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return Response(
            content="""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>An error occurred. Please try again later.</Say>
    <Hangup/>
</Response>""",
            media_type="application/xml",
        )


# ==================== Configuration Instructions ====================

@router.get("/setup-guide")
async def get_setup_guide():
    """Get step-by-step guide for connecting Telnyx with Retell AI."""
    return {
        "title": "Telnyx + Retell AI Integration Guide",
        "overview": (
            "Connect your Telnyx phone numbers to Retell AI voice agents. "
            "Inbound calls will be handled by AI, and outbound calls will route through Telnyx."
        ),
        "prerequisites": [
            "1. Telnyx account with API key (https://portal.telnyx.com)",
            "2. Retell AI account with API key (https://beta.retellai.com)",
            "3. At least one phone number purchased on Telnyx",
            "4. At least one voice agent created in Retell AI",
        ],
        "steps": [
            {
                "step": 1,
                "title": "Configure API Keys",
                "description": "Add your Telnyx and Retell API keys in Settings > Integrations",
            },
            {
                "step": 2,
                "title": "Create Retell Agent",
                "description": "Create a voice agent in Retell AI with your desired prompt and voice",
            },
            {
                "step": 3,
                "title": "Connect Phone Number",
                "description": "Use the 'Connect' button to link a Telnyx number to your Retell agent",
            },
            {
                "step": 4,
                "title": "Configure Telnyx Webhook",
                "description": (
                    "In Telnyx Portal, set your TeXML app's voice URL to: "
                    "https://your-domain.com/api/v1/telnyx-retell/webhook/inbound"
                ),
            },
            {
                "step": 5,
                "title": "Test",
                "description": "Call your Telnyx number - it should be answered by your Retell AI agent!",
            },
        ],
        "webhook_url": "/api/v1/telnyx-retell/webhook/inbound",
    }
