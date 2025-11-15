"""
Voice AI Receptionist Routes
Handles Twilio voice webhooks and OpenAI Realtime API integration
"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64

from main import get_db, User, Lead, Task, Activity, IncomingDataEvent, get_current_user_flexible
from integrations.twilio_voice_service import voice_client, ai_config
import openai

# AI Receptionist Dashboard Integration
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistError,
    AIReceptionistConversation
)
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


# ============================================================================
# INBOUND CALL HANDLING
# ============================================================================

@router.post("/incoming")
async def handle_incoming_call(request: Request, db: Session = Depends(get_db)):
    """
    Twilio webhook for incoming calls
    Returns TwiML to handle the call with AI
    """
    try:
        form_data = await request.form()
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Incoming call from {caller_number} (SID: {call_sid})")

        # Log the call in database
        call_event = IncomingDataEvent(
            source="phone_call",
            external_message_id=call_sid,
            raw_text=f"Incoming call from {caller_number}",
            processed=False,
            metadata={
                "caller": caller_number,
                "direction": "inbound",
                "call_sid": call_sid
            }
        )
        db.add(call_event)

        # ✅ NEW: Log to AI Receptionist Dashboard
        dashboard_activity = AIReceptionistActivity(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            client_phone=caller_number,
            action_type='incoming_call',
            channel='voice',
            outcome_status='pending',
            conversation_id=call_sid,
            extra_data={
                "twilio_call_sid": call_sid,
                "called_number": called_number
            }
        )
        db.add(dashboard_activity)

        db.commit()

        # Generate TwiML response to connect to AI
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        # Fallback to voicemail
        twiml = voice_client.create_voicemail_response()
        return Response(content=str(twiml), media_type="application/xml")


@router.post("/outbound-script")
async def handle_outbound_script(request: Request):
    """
    TwiML for outbound calls
    """
    try:
        query_params = request.query_params
        script_id = query_params.get("script_id")

        logger.info(f"Outbound call script requested: {script_id}")

        # Generate TwiML for outbound call
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error creating outbound script: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")


# ============================================================================
# WEBSOCKET FOR OPENAI REALTIME API
# ============================================================================

@router.websocket("/ws/voice-stream")
async def voice_stream_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket endpoint for Twilio Media Streams -> OpenAI Realtime API
    Handles bidirectional audio streaming for AI conversations
    """
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    # Store call context
    call_context = {
        "call_sid": None,
        "caller_number": None,
        "conversation_history": [],
        "lead_data": {},
        "intent": None
    }

    try:
        # Connect to OpenAI Realtime API
        openai_ws = await connect_to_openai_realtime()

        # Handle bidirectional streaming
        async def twilio_to_openai():
            """Forward audio from Twilio to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data['event'] == 'start':
                        call_context['call_sid'] = data['start']['callSid']
                        call_context['caller_number'] = data['start']['customParameters'].get('From')
                        logger.info(f"Call started: {call_context['call_sid']}")

                    elif data['event'] == 'media':
                        # Forward audio payload to OpenAI
                        audio_payload = data['media']['payload']
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": audio_payload
                        }))

                    elif data['event'] == 'stop':
                        logger.info(f"Call ended: {call_context['call_sid']}")
                        await save_call_summary(call_context, db)
                        break

            except Exception as e:
                logger.error(f"Error in Twilio->OpenAI stream: {e}")

        async def openai_to_twilio():
            """Forward AI responses from OpenAI to Twilio"""
            try:
                async for message in openai_ws:
                    data = json.loads(message)

                    if data['type'] == 'response.audio.delta':
                        # Forward AI audio to Twilio
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": call_context.get('stream_sid'),
                            "media": {
                                "payload": data['delta']
                            }
                        })

                    elif data['type'] == 'response.text.done':
                        # Log conversation
                        call_context['conversation_history'].append({
                            "role": "assistant",
                            "content": data['text']
                        })

                    elif data['type'] == 'conversation.item.input_audio_transcription.completed':
                        # Log what user said
                        call_context['conversation_history'].append({
                            "role": "user",
                            "content": data['transcript']
                        })

                        # Extract lead information
                        await extract_lead_info(data['transcript'], call_context)

            except Exception as e:
                logger.error(f"Error in OpenAI->Twilio stream: {e}")

        # Run both streams concurrently
        await asyncio.gather(
            twilio_to_openai(),
            openai_to_twilio()
        )

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in voice stream: {e}")
    finally:
        try:
            await websocket.close()
            if 'openai_ws' in locals():
                await openai_ws.close()
        except:
            pass


async def connect_to_openai_realtime():
    """Connect to OpenAI Realtime API WebSocket"""
    import websockets

    openai_api_key = openai.api_key
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    ws = await websockets.connect(url, additional_headers=headers)

    # Configure the session
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "alloy",
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            },
            "tools": [
                {
                    "type": "function",
                    "name": "schedule_appointment",
                    "description": "Schedule an appointment with a loan officer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Preferred date (YYYY-MM-DD)"},
                            "time": {"type": "string", "description": "Preferred time (HH:MM)"},
                            "reason": {"type": "string", "description": "Reason for appointment"}
                        },
                        "required": ["date", "time"]
                    }
                },
                {
                    "type": "function",
                    "name": "transfer_to_loan_officer",
                    "description": "Transfer call to a loan officer for urgent matters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Reason for transfer"},
                            "urgency": {"type": "string", "enum": ["low", "medium", "high"]}
                        },
                        "required": ["reason"]
                    }
                },
                {
                    "type": "function",
                    "name": "take_message",
                    "description": "Take a message for the team",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "phone": {"type": "string"},
                            "message": {"type": "string"},
                            "callback_urgency": {"type": "string", "enum": ["urgent", "today", "this_week"]}
                        },
                        "required": ["name", "phone", "message"]
                    }
                }
            ]
        }
    }))

    return ws


async def extract_lead_info(transcript: str, call_context: dict):
    """Extract lead information from conversation using Claude"""
    try:
        # Use Claude to extract structured data from conversation
        import anthropic

        client = anthropic.Anthropic()

        prompt = f"""Extract lead information from this phone conversation transcript:

{transcript}

Previous context: {json.dumps(call_context['conversation_history'][-5:])}

Extract and return JSON with:
- name: caller's name (if mentioned)
- phone: phone number (if mentioned)
- loan_type: purchase/refinance/cash-out/heloc (if discussed)
- property_value: estimated value (if mentioned)
- credit_score: range if mentioned
- urgency: low/medium/high based on timeline
- intent: what they want (quote/appointment/question/etc)

Return ONLY valid JSON, no other text."""

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        lead_data = json.loads(message.content[0].text)
        call_context['lead_data'].update(lead_data)

        logger.info(f"Extracted lead data: {lead_data}")

    except Exception as e:
        logger.error(f"Error extracting lead info: {e}")


async def save_call_summary(call_context: dict, db: Session):
    """Save call summary and create lead/task if needed"""
    try:
        # Create or update lead
        if call_context['lead_data'].get('phone'):
            phone = call_context['lead_data']['phone']

            # Check if lead exists
            lead = db.query(Lead).filter(Lead.phone == phone).first()

            if not lead:
                # Create new lead
                lead = Lead(
                    name=call_context['lead_data'].get('name', 'Phone Inquiry'),
                    phone=phone,
                    source="Phone Call",
                    stage="NEW",
                    notes=f"Inbound call. Conversation summary:\n{json.dumps(call_context['conversation_history'], indent=2)}"
                )
                db.add(lead)
                logger.info(f"Created new lead from call: {phone}")

            # Log activity
            activity = Activity(
                lead_id=lead.id if lead else None,
                activity_type="phone_call",
                description=f"AI Receptionist Call - {call_context.get('intent', 'General Inquiry')}",
                notes=json.dumps(call_context['conversation_history'], indent=2),
                metadata={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data'],
                    "duration": None  # Will be updated by status callback
                }
            )
            db.add(activity)

            # ✅ NEW: Save full conversation to dashboard
            conversation_record = AIReceptionistConversation(
                id=str(uuid.uuid4()),
                started_at=call_context.get('start_time', datetime.now(timezone.utc)),
                ended_at=datetime.now(timezone.utc),
                duration_seconds=call_context.get('duration', 0),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                channel='voice',
                direction='inbound',
                transcript=json.dumps(call_context['conversation_history'], indent=2),
                transcript_json=call_context['conversation_history'],
                summary=call_context.get('intent', 'General inquiry'),
                intent_detected=call_context.get('intent', 'unknown'),
                sentiment='neutral',  # TODO: Add sentiment analysis
                outcome=call_context.get('outcome', 'completed'),
                avg_confidence_score=call_context.get('avg_confidence', 0.85),
                total_turns=len(call_context['conversation_history']),
                extra_data={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data']
                }
            )
            db.add(conversation_record)

            # ✅ NEW: Update activity feed with conversation summary
            activity_update = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                action_type='conversation_summary',
                channel='voice',
                confidence_score=call_context.get('avg_confidence', 0.85),
                ai_version='gpt-4o-realtime-v1',
                outcome_status='success',
                conversation_id=call_context['call_sid'],
                extra_data={
                    "intent": call_context.get('intent'),
                    "lead_data": call_context['lead_data'],
                    "turns": len(call_context['conversation_history'])
                }
            )
            db.add(activity_update)

            db.commit()
            logger.info(f"Saved call summary for {phone}")

    except Exception as e:
        logger.error(f"Error saving call summary: {e}")
        db.rollback()

        # ✅ NEW: Log error to dashboard
        try:
            error_log = AIReceptionistError(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                error_type='api_failure',
                severity='high',
                context=f"Failed to save call summary: {str(e)}",
                conversation_snippet=json.dumps(call_context.get('conversation_history', [])[-3:]),
                conversation_id=call_context.get('call_sid'),
                root_cause='Unknown',
                needs_human_review=True,
                resolution_status='unresolved',
                extra_data={
                    "call_context": str(call_context),
                    "error_message": str(e)
                }
            )
            db.add(error_log)
            db.commit()
        except:
            pass  # Don't fail on error logging


# ============================================================================
# CALL STATUS & RECORDING WEBHOOKS
# ============================================================================

@router.post("/call-status")
async def handle_call_status(request: Request, db: Session = Depends(get_db)):
    """Webhook for call status updates"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        duration = form_data.get("CallDuration", "0")

        logger.info(f"Call {call_sid} status: {call_status}, duration: {duration}s")

        # Update activity with duration
        activity = db.query(Activity).filter(
            Activity.metadata['call_sid'].astext == call_sid
        ).first()

        if activity:
            activity.metadata['duration'] = int(duration)
            activity.metadata['status'] = call_status
            db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling call status: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/recording-ready")
async def handle_recording_ready(request: Request, db: Session = Depends(get_db)):
    """Webhook when call recording is ready"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        recording_url = form_data.get("RecordingUrl")
        recording_sid = form_data.get("RecordingSid")

        logger.info(f"Recording ready for call {call_sid}: {recording_url}")

        # Update activity with recording URL
        activity = db.query(Activity).filter(
            Activity.metadata['call_sid'].astext == call_sid
        ).first()

        if activity:
            activity.metadata['recording_url'] = recording_url
            activity.metadata['recording_sid'] = recording_sid
            db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling recording: {e}")
        return {"status": "error"}


@router.post("/voicemail-transcription")
async def handle_voicemail_transcription(request: Request, db: Session = Depends(get_db)):
    """Webhook for voicemail transcription"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        transcription_text = form_data.get("TranscriptionText", "")
        caller = form_data.get("From", "Unknown")

        logger.info(f"Voicemail transcription from {caller}: {transcription_text[:100]}")

        # Create task for team to follow up
        task = Task(
            title=f"Voicemail from {caller}",
            description=f"Transcription: {transcription_text}",
            status="PENDING",
            priority="MEDIUM",
            metadata={
                "call_sid": call_sid,
                "caller": caller,
                "type": "voicemail"
            }
        )
        db.add(task)
        db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling voicemail transcription: {e}")
        return {"status": "error"}


# ============================================================================
# CALL TRANSFER
# ============================================================================

@router.post("/transfer")
async def handle_transfer(request: Request):
    """Generate TwiML to transfer call"""
    try:
        query_params = request.query_params
        to_number = query_params.get("to")
        reason = query_params.get("reason", "transfer request")

        logger.info(f"Transferring call to {to_number}: {reason}")

        twiml = voice_client.create_transfer_response(to_number, reason)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error creating transfer TwiML: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/transfer-status")
async def handle_transfer_status(request: Request):
    """Handle transfer completion status"""
    try:
        form_data = await request.form()
        dial_call_status = form_data.get("DialCallStatus")

        logger.info(f"Transfer status: {dial_call_status}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling transfer status: {e}")
        return {"status": "error"}


@router.get("/voicemail")
async def voicemail_twiml():
    """Return voicemail TwiML"""
    twiml = voice_client.create_voicemail_response()
    return Response(content=str(twiml), media_type="application/xml")


# ============================================================================
# CALL MANAGEMENT API ENDPOINTS
# ============================================================================

@router.post("/make-call")
async def make_outbound_call(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    """Make an outbound AI call"""
    try:
        data = await request.json()
        to_number = data.get("to_number")
        script_type = data.get("script_type", "default")  # default, follow_up, appointment_reminder
        lead_id = data.get("lead_id")

        if not to_number:
            return {"success": False, "error": "Phone number required"}

        # Make the call
        call_sid = await voice_client.make_outbound_call(
            to_number=to_number,
            script=script_type
        )

        if call_sid:
            # Log the call
            activity = Activity(
                lead_id=lead_id,
                activity_type="phone_call",
                description=f"Outbound AI call - {script_type}",
                notes=f"Call to {to_number}",
                metadata={
                    "call_sid": call_sid,
                    "direction": "outbound",
                    "script_type": script_type,
                    "initiated_by": current_user.id
                }
            )
            db.add(activity)
            db.commit()

            return {
                "success": True,
                "call_sid": call_sid,
                "message": "Call initiated successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate call"
            }

    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        return {"success": False, "error": str(e)}


@router.get("/call-history")
async def get_call_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    limit: int = 50,
    offset: int = 0
):
    """Get call history"""
    try:
        activities = db.query(Activity).filter(
            Activity.activity_type == "phone_call"
        ).order_by(
            Activity.created_at.desc()
        ).offset(offset).limit(limit).all()

        return {
            "calls": [{
                "id": a.id,
                "lead_id": a.lead_id,
                "description": a.description,
                "notes": a.notes,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "metadata": a.metadata
            } for a in activities]
        }

    except Exception as e:
        logger.error(f"Error getting call history: {e}")
        return {"error": str(e)}


@router.get("/call-stats")
async def get_call_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    """Get call statistics"""
    try:
        from sqlalchemy import func
        from datetime import datetime, timedelta

        # Get stats for last 30 days
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        total_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago
        ).scalar()

        inbound_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago,
            Activity.metadata['direction'].astext == 'inbound'
        ).scalar()

        outbound_calls = db.query(func.count(Activity.id)).filter(
            Activity.activity_type == "phone_call",
            Activity.created_at >= thirty_days_ago,
            Activity.metadata['direction'].astext == 'outbound'
        ).scalar()

        # Leads created from calls
        leads_from_calls = db.query(func.count(Lead.id)).filter(
            Lead.source == "Phone Call",
            Lead.created_at >= thirty_days_ago
        ).scalar()

        return {
            "total_calls": total_calls or 0,
            "inbound_calls": inbound_calls or 0,
            "outbound_calls": outbound_calls or 0,
            "leads_generated": leads_from_calls or 0,
            "period": "last_30_days"
        }

    except Exception as e:
        logger.error(f"Error getting call stats: {e}")
        return {
            "total_calls": 0,
            "inbound_calls": 0,
            "outbound_calls": 0,
            "leads_generated": 0,
            "error": str(e)
        }


@router.get("/ai-receptionist-config")
async def get_ai_receptionist_config(current_user: User = Depends(get_current_user_flexible)):
    """Get AI receptionist configuration"""
    return {
        "enabled": voice_client.enabled and voice_client.openai_enabled,
        "business_name": ai_config.business_name,
        "business_hours": ai_config.business_hours,
        "phone_number": voice_client.from_number,
        "features": {
            "answer_calls": True,
            "make_calls": True,
            "transfer_calls": True,
            "take_messages": True,
            "schedule_appointments": True,
            "lead_qualification": True
        }
    }


@router.post("/ai-receptionist-config")
async def update_ai_receptionist_config(
    request: Request,
    current_user: User = Depends(get_current_user_flexible)
):
    """Update AI receptionist configuration"""
    try:
        data = await request.json()

        if "business_name" in data:
            ai_config.business_name = data["business_name"]

        if "business_hours" in data:
            ai_config.business_hours = data["business_hours"]

        return {
            "success": True,
            "message": "Configuration updated"
        }

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return {"success": False, "error": str(e)}
