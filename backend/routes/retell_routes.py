"""
Retell AI Routes

API endpoints for managing Retell AI voice agents, calls, and webhooks.
Replaces ElevenLabs and legacy telephony routes for voice functionality.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from integrations.retell_service import (
    RetellClient,
    RetellAPIError,
    AgentConfig,
    CallConfig,
    RetellVoice,
    get_retell_client,
    create_ai_receptionist_agent,
    create_marketing_agent,
)

# Call Intelligence Integration
try:
    from services.call_intelligence.integration import (
        handle_retell_call_ended,
        CallIntelligenceIntegration,
    )
    CALL_INTELLIGENCE_ENABLED = True
except ImportError:
    CALL_INTELLIGENCE_ENABLED = False
    handle_retell_call_ended = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/retell", tags=["Retell AI"])

# Dependency injection placeholders
User = None
_get_current_user = None

from db import get_db


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user
    User = user_model
    _get_current_user = current_user_func


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ==================== Pydantic Models ====================

class RetellConfigRequest(BaseModel):
    """Request to save Retell API configuration."""
    api_key: str


class CreateAgentRequest(BaseModel):
    """Request to create a new agent."""
    agent_name: str
    voice_id: str = RetellVoice.EMMA.value
    agent_type: str = "custom"  # custom, receptionist, marketing

    # Voice settings
    voice_temperature: float = 0.7
    voice_speed: float = 1.0

    # Behavior settings
    interruption_sensitivity: float = 0.5
    enable_backchannel: bool = True

    # LLM configuration
    system_prompt: Optional[str] = None
    begin_message: Optional[str] = None

    # Metadata
    company_name: Optional[str] = None
    business_hours: Optional[str] = None


class UpdateAgentRequest(BaseModel):
    """Request to update an agent."""
    agent_name: Optional[str] = None
    voice_id: Optional[str] = None
    voice_temperature: Optional[float] = None
    voice_speed: Optional[float] = None
    interruption_sensitivity: Optional[float] = None
    enable_backchannel: Optional[bool] = None


class CreateCallRequest(BaseModel):
    """Request to initiate a call."""
    agent_id: str
    to_number: str
    from_number: Optional[str] = None

    # Dynamic variables for personalization
    client_name: Optional[str] = None
    call_purpose: Optional[str] = None
    specific_goal: Optional[str] = None
    client_info: Optional[str] = None
    talking_points: Optional[str] = None

    # Additional metadata
    lead_id: Optional[str] = None
    loan_id: Optional[str] = None
    campaign_id: Optional[str] = None

    # Settings
    drop_if_machine_detected: bool = False


class CreatePhoneNumberRequest(BaseModel):
    """Request to create/purchase a phone number."""
    agent_id: str
    area_code: Optional[int] = None


class ImportPhoneNumberRequest(BaseModel):
    """Request to import an existing phone number."""
    phone_number: str
    agent_id: str
    termination_uri: Optional[str] = None


class UpdatePhoneNumberRequest(BaseModel):
    """Request to update phone number configuration."""
    agent_id: Optional[str] = None
    inbound_agent_id: Optional[str] = None
    outbound_agent_id: Optional[str] = None


# ==================== Helper Functions ====================

def get_user_retell_key(db: Session, user_id: int) -> Optional[str]:
    """Get user's Retell API key from database."""
    try:
        result = db.execute(
            text("""
            SELECT retell_api_key FROM user_retell_config
            WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        if result and result[0]:
            return result[0]
    except Exception as e:
        # Table might not exist yet
        logger.warning(f"Could not query user_retell_config: {e}")

    # Fall back to environment variable
    return os.getenv("RETELL_API_KEY")


def get_client_for_user(db: Session, user_id: int) -> RetellClient:
    """Get Retell client configured with user's API key."""
    api_key = get_user_retell_key(db, user_id)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Retell AI not configured. Please add your API key."
        )
    return RetellClient(api_key=api_key)


# ==================== Configuration Routes ====================

@router.post("/connect")
async def connect_retell(
    request: RetellConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect/configure Retell AI account."""
    try:
        # Validate API key by listing agents
        client = RetellClient(api_key=request.api_key)
        await client.list_agents()

        # Ensure the table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS user_retell_config (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    retell_api_key TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.commit()
        except Exception as table_e:
            logger.warning(f"Table creation check: {table_e}")
            db.rollback()

        # Save configuration
        db.execute(
            text("""
            INSERT INTO user_retell_config (user_id, retell_api_key, created_at, updated_at)
            VALUES (:user_id, :api_key, :now, :now)
            ON CONFLICT (user_id) DO UPDATE SET
                retell_api_key = :api_key,
                updated_at = :now
            """),
            {
                "user_id": current_user["id"],
                "api_key": request.api_key,
                "now": datetime.utcnow(),
            }
        )
        db.commit()

        return {"status": "connected", "message": "Retell AI connected successfully"}

    except RetellAPIError as e:
        logger.error(f"Retell API error: status={e.status_code}, message={e.message}")
        detail = f"Retell API error: {e.message}"
        if e.status_code == 401:
            detail = "Invalid API key. Please check your key from dashboard.retellai.com"
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.error(f"Error connecting Retell: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to connect")


@router.get("/status")
async def get_retell_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Retell AI connection status."""
    try:
        api_key = get_user_retell_key(db, current_user["id"])

        if not api_key:
            return {"connected": False, "message": "Retell AI not configured"}

        client = RetellClient(api_key=api_key)
        agents = await client.list_agents()
        phone_numbers = await client.list_phone_numbers()

        return {
            "connected": True,
            "agent_count": len(agents) if isinstance(agents, list) else 0,
            "phone_number_count": len(phone_numbers) if isinstance(phone_numbers, list) else 0,
        }
    except RetellAPIError:
        return {"connected": False, "message": "API key invalid or expired"}
    except Exception as e:
        logger.error(f"Error checking Retell status: {e}")
        return {"connected": False, "message": "Connection check failed"}


# ==================== Agent Routes ====================

@router.get("/agents")
async def list_agents(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all Retell AI agents."""
    client = get_client_for_user(db, current_user["id"])

    try:
        agents = await client.list_agents()
        return {"agents": agents}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/agents")
async def create_agent(
    request: CreateAgentRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new Retell AI agent."""
    client = get_client_for_user(db, current_user["id"])

    try:
        if request.agent_type == "receptionist":
            # Use pre-configured receptionist template
            agent = await create_ai_receptionist_agent(
                company_name=request.company_name or "Our Company",
                business_hours=request.business_hours or "Monday-Friday, 9 AM - 6 PM",
                voice_id=request.voice_id,
                api_key=get_user_retell_key(db, current_user["id"]),
            )
        elif request.agent_type == "marketing":
            # Use pre-configured marketing template
            agent = await create_marketing_agent(
                company_name=request.company_name or "Our Company",
                agent_name=request.agent_name,
                voice_id=request.voice_id,
                api_key=get_user_retell_key(db, current_user["id"]),
            )
        else:
            # Custom agent
            # First create LLM if prompt provided
            llm_id = None
            if request.system_prompt:
                llm = await client.create_retell_llm(
                    general_prompt=request.system_prompt,
                    begin_message=request.begin_message,
                )
                llm_id = llm.get("llm_id")

            config = AgentConfig(
                agent_name=request.agent_name,
                voice_id=request.voice_id,
                voice_temperature=request.voice_temperature,
                voice_speed=request.voice_speed,
                interruption_sensitivity=request.interruption_sensitivity,
                enable_backchannel=request.enable_backchannel,
                response_engine={"type": "retell-llm", "llm_id": llm_id} if llm_id else {},
            )

            agent = await client.create_agent(config)

        # Store agent reference in local database
        db.execute(
            text("""
            INSERT INTO retell_agents (
                user_id, retell_agent_id, agent_name, agent_type,
                voice_id, created_at
            ) VALUES (
                :user_id, :agent_id, :agent_name, :agent_type,
                :voice_id, :created_at
            )
            """),
            {
                "user_id": current_user["id"],
                "agent_id": agent.get("agent_id"),
                "agent_name": request.agent_name,
                "agent_type": request.agent_type,
                "voice_id": request.voice_id,
                "created_at": datetime.utcnow(),
            }
        )
        db.commit()

        return agent

    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get agent details."""
    client = get_client_for_user(db, current_user["id"])

    try:
        return await client.get_agent(agent_id)
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an agent."""
    client = get_client_for_user(db, current_user["id"])

    try:
        update_data = request.dict(exclude_unset=True, exclude_none=True)
        return await client.update_agent(agent_id, update_data)
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an agent."""
    client = get_client_for_user(db, current_user["id"])

    try:
        await client.delete_agent(agent_id)

        # Remove from local database
        db.execute(
            text("DELETE FROM retell_agents WHERE retell_agent_id = :agent_id"),
            {"agent_id": agent_id}
        )
        db.commit()

        return {"status": "deleted"}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ==================== Voice Routes ====================

@router.get("/voices")
async def list_voices(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List available voices."""
    client = get_client_for_user(db, current_user["id"])

    try:
        voices = await client.list_voices()
        return {"voices": voices}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ==================== Phone Number Routes ====================

@router.get("/phone-numbers")
async def list_phone_numbers(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all phone numbers."""
    client = get_client_for_user(db, current_user["id"])

    try:
        numbers = await client.list_phone_numbers()
        return {"phone_numbers": numbers}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/phone-numbers")
async def create_phone_number(
    request: CreatePhoneNumberRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Purchase a new phone number."""
    client = get_client_for_user(db, current_user["id"])

    try:
        result = await client.create_phone_number(
            agent_id=request.agent_id,
            area_code=request.area_code,
        )

        # Store phone number reference
        db.execute(
            text("""
            INSERT INTO retell_phone_numbers (
                user_id, phone_number, retell_agent_id, created_at
            ) VALUES (
                :user_id, :phone_number, :agent_id, :created_at
            )
            """),
            {
                "user_id": current_user["id"],
                "phone_number": result.get("phone_number"),
                "agent_id": request.agent_id,
                "created_at": datetime.utcnow(),
            }
        )
        db.commit()

        return result
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/phone-numbers/import")
async def import_phone_number(
    request: ImportPhoneNumberRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import an existing phone number from the telephony provider."""
    client = get_client_for_user(db, current_user["id"])

    try:
        result = await client.import_phone_number(
            phone_number=request.phone_number,
            agent_id=request.agent_id,
            termination_uri=request.termination_uri,
        )

        # Store phone number reference
        db.execute(
            text("""
            INSERT INTO retell_phone_numbers (
                user_id, phone_number, retell_agent_id, imported, created_at
            ) VALUES (
                :user_id, :phone_number, :agent_id, TRUE, :created_at
            )
            """),
            {
                "user_id": current_user["id"],
                "phone_number": request.phone_number,
                "agent_id": request.agent_id,
                "created_at": datetime.utcnow(),
            }
        )
        db.commit()

        return result
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.patch("/phone-numbers/{phone_number}")
async def update_phone_number(
    phone_number: str,
    request: UpdatePhoneNumberRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update phone number configuration."""
    client = get_client_for_user(db, current_user["id"])

    try:
        return await client.update_phone_number(
            phone_number=phone_number,
            agent_id=request.agent_id,
            inbound_agent_id=request.inbound_agent_id,
            outbound_agent_id=request.outbound_agent_id,
        )
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.delete("/phone-numbers/{phone_number}")
async def delete_phone_number(
    phone_number: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete/release a phone number."""
    client = get_client_for_user(db, current_user["id"])

    try:
        await client.delete_phone_number(phone_number)

        # Remove from local database
        db.execute(
            text("DELETE FROM retell_phone_numbers WHERE phone_number = :phone_number"),
            {"phone_number": phone_number}
        )
        db.commit()

        return {"status": "deleted"}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ==================== Call Routes ====================

@router.post("/calls")
async def create_call(
    request: CreateCallRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate an outbound call."""
    client = get_client_for_user(db, current_user["id"])

    try:
        # Build dynamic variables
        dynamic_variables = {}
        if request.client_name:
            dynamic_variables["client_name"] = request.client_name
        if request.call_purpose:
            dynamic_variables["call_purpose"] = request.call_purpose
        if request.specific_goal:
            dynamic_variables["specific_goal"] = request.specific_goal
        if request.client_info:
            dynamic_variables["client_info"] = request.client_info
        if request.talking_points:
            dynamic_variables["talking_points"] = request.talking_points

        # Build metadata
        metadata = {}
        if request.lead_id:
            metadata["lead_id"] = request.lead_id
        if request.loan_id:
            metadata["loan_id"] = request.loan_id
        if request.campaign_id:
            metadata["campaign_id"] = request.campaign_id
        metadata["user_id"] = str(current_user["id"])

        config = CallConfig(
            agent_id=request.agent_id,
            to_number=request.to_number,
            from_number=request.from_number,
            dynamic_variables=dynamic_variables,
            drop_if_machine_detected=request.drop_if_machine_detected,
            metadata=metadata,
        )

        result = await client.create_call(config)

        # Store call record
        db.execute(
            text("""
            INSERT INTO retell_calls (
                user_id, retell_call_id, retell_agent_id,
                to_number, from_number, direction,
                lead_id, loan_id, campaign_id,
                status, created_at
            ) VALUES (
                :user_id, :call_id, :agent_id,
                :to_number, :from_number, 'outbound',
                :lead_id, :loan_id, :campaign_id,
                'initiated', :created_at
            )
            """),
            {
                "user_id": current_user["id"],
                "call_id": result.get("call_id"),
                "agent_id": request.agent_id,
                "to_number": request.to_number,
                "from_number": request.from_number,
                "lead_id": request.lead_id,
                "loan_id": request.loan_id,
                "campaign_id": request.campaign_id,
                "created_at": datetime.utcnow(),
            }
        )
        db.commit()

        return result

    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/calls")
async def list_calls(
    limit: int = 50,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List recent calls."""
    client = get_client_for_user(db, current_user["id"])

    try:
        filter_criteria = {}
        if agent_id:
            filter_criteria["agent_id"] = agent_id

        calls = await client.list_calls(
            filter_criteria=filter_criteria,
            limit=limit,
        )
        return {"calls": calls}
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get call details."""
    client = get_client_for_user(db, current_user["id"])

    try:
        return await client.get_call(call_id)
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """End an active call."""
    client = get_client_for_user(db, current_user["id"])

    try:
        result = await client.end_call(call_id)

        # Update local record
        db.execute(
            text("""
            UPDATE retell_calls
            SET status = 'ended', ended_at = :now
            WHERE retell_call_id = :call_id
            """),
            {"call_id": call_id, "now": datetime.utcnow()}
        )
        db.commit()

        return result
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.post("/calls/{call_id}/transfer")
async def transfer_call(
    call_id: str,
    transfer_to: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transfer an active call."""
    client = get_client_for_user(db, current_user["id"])

    try:
        return await client.transfer_call(call_id, transfer_to)
    except RetellAPIError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ==================== Webhook Routes ====================

@router.post("/webhooks/call-events")
async def handle_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Handle Retell AI webhooks for call events.

    Events:
    - call_started: Call has been initiated
    - call_ended: Call has ended
    - call_analyzed: Post-call analysis complete
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("X-Retell-Signature", "")

        # Verify signature — fail-closed when not configured
        api_key = os.getenv("RETELL_API_KEY")
        if not api_key:
            logger.error("RETELL_API_KEY not configured — rejecting webhook")
            raise HTTPException(status_code=401, detail="Webhook verification not configured")
        if not signature:
            logger.warning("Missing X-Retell-Signature header")
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        if not RetellClient.verify_webhook_signature(body, signature, api_key):
            logger.warning("Invalid Retell webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse event
        event = await request.json()
        event_type = event.get("event")
        call_data = event.get("call", {})
        call_id = call_data.get("call_id")

        logger.info(f"Retell webhook received: {event_type} for call {call_id}")

        if event_type == "call_started":
            # Update call status
            db.execute(
                text("""
                UPDATE retell_calls
                SET status = 'in_progress', started_at = :now
                WHERE retell_call_id = :call_id
                """),
                {"call_id": call_id, "now": datetime.utcnow()}
            )

        elif event_type == "call_ended":
            # Update call with end data
            db.execute(
                text("""
                UPDATE retell_calls
                SET status = 'completed',
                    ended_at = :now,
                    duration_seconds = :duration,
                    disconnection_reason = :reason
                WHERE retell_call_id = :call_id
                """),
                {
                    "call_id": call_id,
                    "now": datetime.utcnow(),
                    "duration": call_data.get("call_duration_ms", 0) / 1000,
                    "reason": call_data.get("disconnection_reason"),
                }
            )

        elif event_type == "call_analyzed":
            # Store analysis results
            analysis = call_data.get("call_analysis", {})
            transcript = call_data.get("transcript", "")

            db.execute(
                text("""
                UPDATE retell_calls
                SET transcript = :transcript,
                    call_summary = :summary,
                    user_sentiment = :sentiment,
                    call_successful = :successful,
                    custom_analysis = :custom
                WHERE retell_call_id = :call_id
                """),
                {
                    "call_id": call_id,
                    "transcript": transcript,
                    "summary": analysis.get("call_summary"),
                    "sentiment": analysis.get("user_sentiment"),
                    "successful": analysis.get("call_successful"),
                    "custom": str(analysis.get("custom_analysis_data", {})),
                }
            )

            # Trigger post-call processing
            background_tasks.add_task(
                process_call_completion,
                call_id=call_id,
                call_data=call_data,
                db=db,
            )

        db.commit()
        return {"status": "processed"}

    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_call_completion(
    call_id: str,
    call_data: Dict[str, Any],
    db: Session,
):
    """
    Process completed call data.
    - Update lead/contact records
    - Log activity
    - Trigger Call Intelligence processing
    - Trigger follow-up workflows
    """
    try:
        # Get local call record with metadata
        call_record = db.execute(
            text("""
            SELECT lead_id, loan_id, campaign_id, user_id, organization_id
            FROM retell_calls WHERE retell_call_id = :call_id
            """),
            {"call_id": call_id}
        ).fetchone()

        if not call_record:
            return

        # Update lead last contact if applicable
        if call_record.lead_id:
            db.execute(
                text("""
                UPDATE leads
                SET last_contact_at = :now, last_contact_method = 'phone'
                WHERE id = :lead_id
                """),
                {"lead_id": call_record.lead_id, "now": datetime.utcnow()}
            )

        # Log activity
        analysis = call_data.get("call_analysis", {})
        db.execute(
            text("""
            INSERT INTO activities (
                user_id, activity_type, subject, description,
                lead_id, loan_id, created_at
            ) VALUES (
                :user_id, 'ai_call', 'AI Voice Call',
                :description, :lead_id, :loan_id, :created_at
            )
            """),
            {
                "user_id": call_record.user_id,
                "description": analysis.get("call_summary", "AI voice call completed"),
                "lead_id": call_record.lead_id,
                "loan_id": call_record.loan_id,
                "created_at": datetime.utcnow(),
            }
        )

        db.commit()

        # Process through Call Intelligence if enabled and transcript available
        if CALL_INTELLIGENCE_ENABLED and handle_retell_call_ended:
            transcript = call_data.get("transcript", "")
            if transcript:
                logger.info(f"Processing call {call_id} through Call Intelligence")
                try:
                    ci_result = await handle_retell_call_ended(
                        db=db,
                        call_id=call_id,
                        call_data=call_data,
                    )

                    if ci_result.get("success"):
                        logger.info(
                            f"Call Intelligence processed {call_id}: "
                            f"{ci_result.get('extractions_count', 0)} extractions, "
                            f"{ci_result.get('tasks_created', 0)} tasks created"
                        )
                    else:
                        logger.warning(
                            f"Call Intelligence processing failed for {call_id}: "
                            f"{ci_result.get('error', 'Unknown error')}"
                        )
                except Exception as ci_error:
                    logger.exception(f"Call Intelligence error for {call_id}: {ci_error}")
            else:
                logger.debug(f"No transcript available for call {call_id}, skipping Call Intelligence")

        logger.info(f"Post-call processing complete for {call_id}")

    except Exception as e:
        logger.exception(f"Post-call processing error: {e}")


# ==================== Analytics Routes ====================

@router.get("/analytics/calls")
async def get_call_analytics(
    days: int = 30,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get call analytics."""
    filters = ["user_id = :user_id", f"created_at >= CURRENT_DATE - {days}"]
    params = {"user_id": current_user["id"]}

    if agent_id:
        filters.append("retell_agent_id = :agent_id")
        params["agent_id"] = agent_id

    where_clause = " AND ".join(filters)

    # Get summary stats
    stats = db.execute(
        text(f"""
        SELECT
            COUNT(*) as total_calls,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_calls,
            AVG(duration_seconds) as avg_duration,
            COUNT(CASE WHEN call_successful = TRUE THEN 1 END) as successful_calls
        FROM retell_calls
        WHERE {where_clause}
        """),
        params
    ).fetchone()

    # Get calls by day
    daily = db.execute(
        text(f"""
        SELECT
            DATE(created_at) as date,
            COUNT(*) as count
        FROM retell_calls
        WHERE {where_clause}
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 30
        """),
        params
    ).fetchall()

    return {
        "summary": {
            "total_calls": stats[0] or 0,
            "completed_calls": stats[1] or 0,
            "avg_duration_seconds": round(stats[2] or 0, 1),
            "successful_calls": stats[3] or 0,
            "success_rate": round((stats[3] or 0) / (stats[1] or 1) * 100, 1),
        },
        "daily": [{"date": str(d[0]), "count": d[1]} for d in daily],
    }
