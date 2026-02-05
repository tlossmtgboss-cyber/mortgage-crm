"""
Voicemail Drop Routes

This module contains all API endpoints for the voicemail drop system.
Extracted from main.py for better code organization.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import or_

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voicemail", tags=["Voicemail Drop"])


# =============================================================================
# Runtime Import Helpers
# =============================================================================

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Get current user - wrapper that imports from main at runtime to avoid circular imports.
    """
    import main

    # Get token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    # Fall back to query param
    if not token:
        token = request.query_params.get("token", "")

    return await main.get_current_user(token=token, request=request, db=db)


def get_voicemail_drop_model():
    """Get VoicemailDrop model - imports from main at runtime"""
    import main
    return main.VoicemailDrop


def get_voicemail_event_model():
    """Get VoicemailEvent model - imports from main at runtime"""
    import main
    return main.VoicemailEvent


def get_voicemail_template_model():
    """Get VoicemailTemplate model - imports from main at runtime"""
    import main
    return main.VoicemailTemplate


# =============================================================================
# Helper Functions
# =============================================================================

async def send_voicemail_via_vapi(
    phone_number: str,
    message: str,
    recipient_name: str,
    user_name: str,
    voicemail_drop_id: int,
    db: Session
) -> dict:
    """Helper function to send voicemail using Vapi AI"""
    import httpx

    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")

    if not vapi_api_key:
        raise HTTPException(status_code=503, detail="Vapi API key not configured")

    # Format phone number to E.164 format
    clean_number = ''.join(filter(str.isdigit, phone_number))
    if len(clean_number) == 10:
        clean_number = f"+1{clean_number}"
    elif len(clean_number) == 11 and clean_number.startswith('1'):
        clean_number = f"+{clean_number}"

    # Create voicemail assistant configuration
    greeting = f"Hi {recipient_name}, " if recipient_name else "Hello, "
    full_message = (
        f"{greeting}this is calling from {user_name}'s office. "
        f"{message} "
        f"Feel free to call us back at your convenience. Have a great day!"
    )

    # Vapi call configuration
    vapi_payload = {
        "phoneNumberId": vapi_assistant_id,
        "customer": {
            "number": clean_number,
            "name": recipient_name
        },
        "assistantOverrides": {
            "firstMessage": full_message,
            "model": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "paula"  # Natural, professional female voice
            },
            "endCallFunctionEnabled": True,
            "endCallMessage": "Thank you, goodbye!",
            "voicemailDetection": {
                "enabled": True,
                "machineDetectionTimeout": 3000,
                "voicemailMessage": full_message
            }
        },
        "metadata": {
            "voicemail_drop_id": voicemail_drop_id,
            "type": "voicemail_drop"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.vapi.ai/call/phone",
                headers={
                    "Authorization": f"Bearer {vapi_api_key}",
                    "Content-Type": "application/json"
                },
                json=vapi_payload
            )

            if response.status_code not in [200, 201]:
                error_msg = response.text
                logger.error(f"Vapi API error: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Vapi error: {error_msg}")

            result = response.json()
            call_id = result.get("id")

            logger.info(f"Vapi call initiated: {call_id}")

            return {
                "success": True,
                "call_id": call_id,
                "vapi_response": result
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling Vapi: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/drop")
async def create_voicemail_drop(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Create and send a single voicemail drop

    Request body:
    {
        "phone_number": "925-389-6782",
        "recipient_name": "John Doe",
        "message": "Your closing documents are ready",
        "lead_id": 123,  // optional
        "loan_id": 456,  // optional
        "template_id": 1  // optional
    }
    """
    VoicemailDrop = get_voicemail_drop_model()
    VoicemailEvent = get_voicemail_event_model()

    try:
        data = await request.json()

        phone_number = data.get("phone_number")
        recipient_name = data.get("recipient_name", "")
        message = data.get("message")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        template_id = data.get("template_id")

        if not phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Create voicemail drop record
        voicemail_drop = VoicemailDrop(
            user_id=current_user.id,
            lead_id=lead_id,
            loan_id=loan_id,
            template_id=template_id,
            contact_name=recipient_name,
            phone_number=phone_number,
            message_text=message,
            status='pending'
        )
        db.add(voicemail_drop)
        db.commit()
        db.refresh(voicemail_drop)

        # Create event
        event = VoicemailEvent(
            voicemail_drop_id=voicemail_drop.id,
            event_type='queued',
            event_data={"message": "Voicemail queued for delivery"}
        )
        db.add(event)
        db.commit()

        # Send voicemail via Vapi
        try:
            vapi_result = await send_voicemail_via_vapi(
                phone_number=phone_number,
                message=message,
                recipient_name=recipient_name,
                user_name=current_user.full_name or "your loan officer",
                voicemail_drop_id=voicemail_drop.id,
                db=db
            )

            # Update voicemail drop with Vapi call ID
            voicemail_drop.vapi_call_id = vapi_result.get("call_id")
            voicemail_drop.status = 'calling'
            voicemail_drop.delivery_attempts = 1
            voicemail_drop.last_attempt_at = datetime.now(timezone.utc)
            db.commit()

            # Create calling event
            calling_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='calling',
                event_data={"vapi_call_id": vapi_result.get("call_id")}
            )
            db.add(calling_event)
            db.commit()

            logger.info(f"Voicemail drop {voicemail_drop.id} initiated successfully")

            return {
                "success": True,
                "voicemail_drop_id": voicemail_drop.id,
                "vapi_call_id": vapi_result.get("call_id"),
                "status": "calling",
                "message": "Voicemail is being delivered"
            }

        except Exception as e:
            # Update voicemail drop with error
            voicemail_drop.status = 'failed'
            voicemail_drop.error_message = str(e)
            db.commit()

            # Create failed event
            failed_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='failed',
                event_data={"error": str(e)}
            )
            db.add(failed_event)
            db.commit()

            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating voicemail drop: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe")
async def transcribe_voice_message(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Transcribe voice recording using OpenAI Whisper

    Request body should be multipart/form-data with:
    - audio_file: The audio file to transcribe
    """
    try:
        import httpx

        form_data = await request.form()
        audio_file = form_data.get("audio_file")

        if not audio_file:
            raise HTTPException(status_code=400, detail="Audio file is required")

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        # Read audio file
        audio_data = await audio_file.read()

        # Call OpenAI Whisper API
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                'file': ('audio.webm', audio_data, 'audio/webm'),
                'model': (None, 'whisper-1')
            }

            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {openai_api_key}"
                },
                files=files
            )

            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Whisper API error: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Transcription failed: {error_msg}")

            result = response.json()
            transcription = result.get("text", "")

            logger.info(f"Transcribed voice message: {transcription[:100]}...")

            return {
                "success": True,
                "transcription": transcription
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing voice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_voicemail_templates(
    category: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail templates (default templates + user's custom templates)"""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        query = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.is_active == True
        ).filter(
            or_(
                VoicemailTemplate.user_id == None,  # Default templates
                VoicemailTemplate.user_id == current_user.id  # User's templates
            )
        )

        if category:
            query = query.filter(VoicemailTemplate.category == category)

        templates = query.order_by(
            VoicemailTemplate.is_default.desc(),
            VoicemailTemplate.name
        ).all()

        return {
            "success": True,
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "category": t.category,
                    "message_text": t.message_text,
                    "variables": t.variables,
                    "is_default": t.is_default,
                    "times_used": t.times_used,
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None
                }
                for t in templates
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates")
async def create_voicemail_template(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new voicemail template"""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        data = await request.json()

        name = data.get("name")
        category = data.get("category", "custom")
        message_text = data.get("message_text")
        variables = data.get("variables", [])

        if not name:
            raise HTTPException(status_code=400, detail="Template name is required")

        if not message_text:
            raise HTTPException(status_code=400, detail="Message text is required")

        template = VoicemailTemplate(
            user_id=current_user.id,
            name=name,
            category=category,
            message_text=message_text,
            variables=variables,
            is_active=True,
            is_default=False
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info(f"Created voicemail template {template.id} for user {current_user.id}")

        return {
            "success": True,
            "template": {
                "id": template.id,
                "name": template.name,
                "category": template.category,
                "message_text": template.message_text,
                "variables": template.variables
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_voicemail_history(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail drop history for current user"""
    VoicemailDrop = get_voicemail_drop_model()

    try:
        query = db.query(VoicemailDrop).filter(
            VoicemailDrop.user_id == current_user.id
        )

        if status:
            query = query.filter(VoicemailDrop.status == status)

        total = query.count()

        voicemails = query.order_by(
            VoicemailDrop.created_at.desc()
        ).offset(offset).limit(limit).all()

        return {
            "success": True,
            "total": total,
            "voicemails": [
                {
                    "id": vm.id,
                    "contact_name": vm.contact_name,
                    "phone_number": vm.phone_number,
                    "message_text": vm.message_text,
                    "status": vm.status,
                    "created_at": vm.created_at.isoformat(),
                    "delivered_at": vm.delivered_at.isoformat() if vm.delivered_at else None,
                    "call_duration": vm.call_duration,
                    "call_cost": float(vm.call_cost) if vm.call_cost else None,
                    "callback_received": vm.callback_received,
                    "error_message": vm.error_message
                }
                for vm in voicemails
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching voicemail history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_voicemail_analytics(
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail analytics for current user"""
    VoicemailDrop = get_voicemail_drop_model()

    try:
        # Default to last 30 days
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        if not end_date:
            end_date = datetime.now(timezone.utc).isoformat()

        # Parse dates
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # Get stats
        query = db.query(VoicemailDrop).filter(
            VoicemailDrop.user_id == current_user.id,
            VoicemailDrop.created_at >= start,
            VoicemailDrop.created_at <= end
        )

        total_sent = query.count()
        delivered = query.filter(VoicemailDrop.status == 'delivered').count()
        failed = query.filter(VoicemailDrop.status == 'failed').count()
        callbacks = query.filter(VoicemailDrop.callback_received == True).count()

        # Calculate total cost
        cost_result = query.with_entities(
            func.sum(VoicemailDrop.call_cost)
        ).scalar()
        total_cost = float(cost_result) if cost_result else 0.0

        # Calculate average duration
        duration_result = query.filter(
            VoicemailDrop.call_duration != None
        ).with_entities(
            func.avg(VoicemailDrop.call_duration)
        ).scalar()
        avg_duration = int(duration_result) if duration_result else 0

        # Delivery rate
        delivery_rate = (delivered / total_sent * 100) if total_sent > 0 else 0

        # Callback rate
        callback_rate = (callbacks / delivered * 100) if delivered > 0 else 0

        return {
            "success": True,
            "analytics": {
                "total_sent": total_sent,
                "delivered": delivered,
                "failed": failed,
                "callbacks_received": callbacks,
                "delivery_rate": round(delivery_rate, 2),
                "callback_rate": round(callback_rate, 2),
                "total_cost": round(total_cost, 2),
                "average_duration_seconds": avg_duration,
                "period": {
                    "start": start_date,
                    "end": end_date
                }
            }
        }

    except Exception as e:
        logger.error(f"Error fetching analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
