"""
Vapi AI Receptionist - FastAPI Routes
Webhook handlers and API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging

from database import get_db
from vapi_service import VapiService, VapiCRMIntegration
from vapi_models import VapiCall, VapiCallNote, VapiAssistant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vapi", tags=["vapi"])


def get_current_user_flexible():
    """Lazy import auth dependency"""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


# Pydantic Models
class VapiWebhookPayload(BaseModel):
    """Vapi webhook payload"""
    message: Dict[str, Any]


class CallResponse(BaseModel):
    """Call response model"""
    id: int
    vapi_call_id: str
    phone_number: Optional[str] = None
    caller_name: Optional[str] = None
    status: str
    duration: Optional[int] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    sentiment: Optional[str] = None
    lead_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateOutboundCallRequest(BaseModel):
    """Request to create outbound call"""
    lead_id: int
    assistant_id: str
    purpose: Optional[str] = "follow_up"


class AssistantConfigRequest(BaseModel):
    """Create/Update assistant configuration"""
    name: str
    first_message: str
    system_prompt: str
    voice_id: Optional[str] = "jennifer-playht"
    language: Optional[str] = "en"


# Webhook Endpoints (No Auth - Vapi webhooks)
@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Main Vapi webhook endpoint
    Handles all webhook events from Vapi (calls, transcripts, etc.)
    """
    try:
        payload = await request.json()
        logger.info(f"Vapi webhook received: {payload.get('message', {}).get('type')}")

        # Process webhook in background to return 200 quickly
        background_tasks.add_task(process_webhook_background, payload, db)

        # Vapi expects 200 OK response quickly
        return JSONResponse(
            status_code=200,
            content={"status": "received"}
        )

    except Exception as e:
        # Log error but still return 200 to Vapi
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": str(e)}
        )


async def process_webhook_background(payload: Dict[str, Any], db: Session):
    """Process webhook in background task"""
    try:
        integration = VapiCRMIntegration(db)
        await integration.process_call_webhook(payload)
        logger.info("Webhook processed successfully")
    except Exception as e:
        logger.error(f"Background webhook processing error: {str(e)}")


@router.post("/webhook/assistant-request")
async def assistant_request_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle assistant-request webhook
    Used to provide dynamic assistant configuration per call
    """
    try:
        payload = await request.json()
        call_data = payload.get("message", {}).get("call", {})
        phone_number = call_data.get("phoneNumber")

        logger.info(f"Assistant request for phone: {phone_number}")

        # Customize assistant behavior based on caller
        try:
            from main import Lead
            lead = db.query(Lead).filter(Lead.phone == phone_number).first()

            if lead:
                # Existing customer
                return {
                    "assistant": {
                        "firstMessage": f"Hello {lead.first_name}! Thanks for calling back. How can I help you today?",
                        "model": {
                            "messages": [{
                                "role": "system",
                                "content": f"You are speaking with {lead.first_name} {lead.last_name}, an existing customer. Be warm and personalized."
                            }]
                        }
                    }
                }
        except Exception as e:
            logger.warning(f"Could not fetch lead data: {e}")

        # New caller
        return {
            "assistant": {
                "firstMessage": "Hello! Thank you for calling CMG Home Loans. I'm your AI assistant. How can I help you today?",
                "model": {
                    "messages": [{
                        "role": "system",
                        "content": "You are a professional mortgage company receptionist. Be welcoming and gather their information politely."
                    }]
                }
            }
        }

    except Exception as e:
        logger.error(f"Assistant request error: {str(e)}")
        return JSONResponse(status_code=200, content={})


# Authenticated Endpoints
@router.get("/calls", response_model=List[CallResponse])
async def get_calls(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get all Vapi calls with filtering"""
    query = db.query(VapiCall).order_by(VapiCall.created_at.desc())

    if status:
        query = query.filter(VapiCall.status == status)

    calls = query.offset(skip).limit(limit).all()
    return calls


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get specific call details"""
    call = db.query(VapiCall).filter(VapiCall.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.get("/calls/{call_id}/transcript")
async def get_call_transcript(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get formatted call transcript"""
    call = db.query(VapiCall).filter(VapiCall.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "call_id": call.id,
        "vapi_call_id": call.vapi_call_id,
        "phone_number": call.phone_number,
        "transcript": call.transcript,
        "summary": call.summary,
        "duration": call.duration,
        "sentiment": call.sentiment
    }


@router.get("/calls/{call_id}/notes")
async def get_call_notes(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get action items and notes from call"""
    notes = db.query(VapiCallNote).filter(
        VapiCallNote.call_id == call_id
    ).all()

    return {
        "call_id": call_id,
        "notes": [
            {
                "id": note.id,
                "note_type": note.note_type,
                "content": note.content,
                "priority": note.priority,
                "completed": note.completed,
                "due_date": note.due_date.isoformat() if note.due_date else None,
                "created_at": note.created_at.isoformat() if note.created_at else None
            }
            for note in notes
        ]
    }


@router.post("/calls/outbound")
async def create_outbound_call(
    request: CreateOutboundCallRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Initiate outbound call to a lead"""
    integration = VapiCRMIntegration(db)

    try:
        vapi_call = await integration.create_outbound_call(
            lead_id=request.lead_id,
            assistant_id=request.assistant_id,
            purpose=request.purpose
        )

        return {
            "success": True,
            "call_id": vapi_call.id,
            "vapi_call_id": vapi_call.vapi_call_id,
            "status": vapi_call.status
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Outbound call error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create call: {str(e)}")


@router.get("/stats/daily")
async def get_daily_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get daily call statistics"""
    from sqlalchemy import func

    start_date = datetime.utcnow() - timedelta(days=days)

    stats = db.query(
        func.date(VapiCall.created_at).label('date'),
        func.count(VapiCall.id).label('total_calls'),
        func.sum(VapiCall.duration).label('total_duration'),
        func.avg(VapiCall.duration).label('avg_duration')
    ).filter(
        VapiCall.created_at >= start_date
    ).group_by(
        func.date(VapiCall.created_at)
    ).all()

    return {
        "period_days": days,
        "stats": [
            {
                "date": str(stat.date),
                "total_calls": stat.total_calls,
                "total_duration": stat.total_duration or 0,
                "avg_duration": float(stat.avg_duration) if stat.avg_duration else 0
            }
            for stat in stats
        ]
    }


@router.get("/stats/sentiment")
async def get_sentiment_analysis(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get sentiment analysis of calls"""
    from sqlalchemy import func

    start_date = datetime.utcnow() - timedelta(days=days)

    sentiment_stats = db.query(
        VapiCall.sentiment,
        func.count(VapiCall.id).label('count')
    ).filter(
        VapiCall.created_at >= start_date,
        VapiCall.sentiment.isnot(None)
    ).group_by(
        VapiCall.sentiment
    ).all()

    return {
        "period_days": days,
        "sentiment_distribution": {
            stat.sentiment: stat.count
            for stat in sentiment_stats
        }
    }


# Assistant Management
@router.post("/assistants")
async def create_assistant(
    config: AssistantConfigRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create new Vapi assistant"""
    vapi = VapiService()

    try:
        response = await vapi.create_assistant(
            name=config.name,
            first_message=config.first_message,
            system_prompt=config.system_prompt,
            voice_id=config.voice_id
        )

        # Save to database
        assistant = VapiAssistant(
            vapi_assistant_id=response.get("id"),
            name=config.name,
            first_message=config.first_message,
            system_prompt=config.system_prompt,
            voice_id=config.voice_id,
            language=config.language,
            config=response
        )

        db.add(assistant)
        db.commit()
        db.refresh(assistant)

        return {
            "success": True,
            "assistant": {
                "id": assistant.id,
                "vapi_id": assistant.vapi_assistant_id,
                "name": assistant.name
            }
        }

    except Exception as e:
        logger.error(f"Create assistant error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create assistant: {str(e)}")


@router.get("/assistants")
async def list_assistants(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """List all configured assistants"""
    assistants = db.query(VapiAssistant).filter(
        VapiAssistant.is_active == True
    ).all()

    return {
        "assistants": [
            {
                "id": a.id,
                "vapi_id": a.vapi_assistant_id,
                "name": a.name,
                "description": a.description,
                "total_calls": a.total_calls,
                "total_minutes": a.total_minutes
            }
            for a in assistants
        ]
    }


@router.get("/config")
async def get_vapi_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get Vapi configuration status"""
    import os

    has_api_key = bool(os.getenv("VAPI_API_KEY"))

    # Count total calls
    from sqlalchemy import func
    total_calls = db.query(func.count(VapiCall.id)).scalar() or 0
    active_assistants = db.query(func.count(VapiAssistant.id)).filter(
        VapiAssistant.is_active == True
    ).scalar() or 0

    return {
        "enabled": has_api_key,
        "total_calls": total_calls,
        "active_assistants": active_assistants,
        "webhook_url": f"{os.getenv('PRODUCTION_DOMAIN', 'localhost')}/api/vapi/webhook"
    }
