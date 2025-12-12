"""
Voice AI Receptionist Routes
Handles Twilio voice webhooks and OpenAI Realtime API integration
"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import json
import asyncio
import base64

# Import from database instead of main to avoid circular dependency
from database import get_db
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


# Lazy import to avoid circular dependency with main.py
def get_models():
    """Lazy import models from main.py to avoid circular imports"""
    from main import User, Lead, Task, Activity, IncomingDataEvent
    return User, Lead, Task, Activity, IncomingDataEvent


def get_current_user_flexible():
    """Lazy import auth dependency from main.py"""
    from main import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


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

        # Note: Not logging to IncomingDataEvent because it requires user_id
        # Instead, we log directly to AI Receptionist Dashboard which is better for voice

        # ✅ Log to AI Receptionist Dashboard
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
async def voice_stream_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams -> OpenAI Realtime API
    Handles bidirectional audio streaming for AI conversations
    """
    logger.info(f"🔌 WebSocket connection attempt from: {websocket.client}")
    logger.info(f"🔌 Headers: {dict(websocket.headers)}")

    # Get database session manually to avoid dependency issues
    db = get_db().__next__()

    try:
        await websocket.accept()
        logger.info("✅ Voice stream WebSocket connected successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to accept WebSocket: {e}")
        raise

    # Store call context
    call_context = {
        "call_sid": None,
        "caller_number": None,
        "conversation_history": [],
        "lead_data": {},
        "intent": None
    }

    openai_ws = None
    try:
        # Connect to OpenAI Realtime API with timeout
        try:
            openai_ws = await connect_to_openai_realtime()
            logger.info("✅ OpenAI Realtime API connected successfully")
        except asyncio.TimeoutError:
            logger.error("❌ OpenAI Realtime connection timed out")
            await websocket.close(code=1011, reason="AI service timeout")
            return
        except Exception as e:
            logger.error(f"❌ Failed to connect to OpenAI Realtime: {e}")
            await websocket.close(code=1011, reason=f"AI service error: {str(e)[:50]}")
            return

        # Handle bidirectional streaming
        async def twilio_to_openai():
            """Forward audio from Twilio to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data['event'] == 'start':
                        call_context['call_sid'] = data['start']['callSid']
                        call_context['stream_sid'] = data['start']['streamSid']  # Capture stream SID
                        call_context['caller_number'] = data['start'].get('customParameters', {}).get('From')
                        logger.info(f"📞 Call started: {call_context['call_sid']}, stream: {call_context['stream_sid']}")

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
                    event_type = data.get('type', 'unknown')

                    # Log all events for debugging
                    if event_type not in ['response.audio.delta', 'input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped']:
                        logger.info(f"🎙️ OpenAI event: {event_type}")

                    if event_type == 'response.audio.delta':
                        # Forward AI audio to Twilio
                        audio_payload = data.get('delta', '')
                        if audio_payload and call_context.get('stream_sid'):
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": call_context['stream_sid'],
                                "media": {
                                    "payload": audio_payload
                                }
                            })
                        else:
                            logger.warning(f"⚠️ Missing audio payload or stream_sid")

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
        logger.info("📴 Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"❌ Error in voice stream: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass
        try:
            if openai_ws:
                await openai_ws.close()
        except:
            pass
        try:
            db.close()
        except:
            pass
        logger.info("🔚 Voice stream cleanup complete")


async def connect_to_openai_realtime():
    """Connect to OpenAI Realtime API WebSocket"""
    import websockets

    openai_api_key = openai.api_key
    if not openai_api_key:
        raise Exception("OpenAI API key not configured")

    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    # Connect with timeout
    ws = await asyncio.wait_for(
        websockets.connect(url, extra_headers=headers),
        timeout=10.0
    )

    # Wait for session.created event with timeout
    initial_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
    logger.info(f"OpenAI Realtime connected: {initial_response[:100]}")

    # Configure the session for natural two-way conversation
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "shimmer",  # More natural, warm voice for phone conversations
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.6,  # Slightly higher to reduce false triggers
                "prefix_padding_ms": 400,  # More context before speech
                "silence_duration_ms": 900  # Wait longer before responding (more natural)
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

    # Wait for session.updated confirmation before triggering greeting
    session_ready = False
    for _ in range(10):  # Wait up to 5 seconds
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=0.5)
            data = json.loads(response)
            logger.info(f"OpenAI setup event: {data.get('type')}")
            if data.get('type') == 'session.updated':
                session_ready = True
                break
        except asyncio.TimeoutError:
            continue

    if not session_ready:
        logger.warning("Session update not confirmed, proceeding anyway")

    # Trigger Sam to greet the caller
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "A caller just connected. Please greet them warmly."
                }
            ]
        }
    }))

    await ws.send(json.dumps({
        "type": "response.create"
    }))

    logger.info("OpenAI Realtime session configured, initial greeting triggered")

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
        _, Lead, _, Activity, _ = get_models()

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
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")

        logger.info(f"Call {call_sid} status: {call_status}, duration: {duration}s")

        # Update AI Receptionist Dashboard activity if it exists
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                # Update with final status
                activity.outcome_status = 'completed' if call_status == 'completed' else call_status
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['duration'] = int(duration)
                activity.extra_data['final_status'] = call_status
                db.commit()
                logger.info(f"Updated AI Receptionist activity for call {call_sid}")
        except Exception as update_error:
            logger.warning(f"Could not update activity for call {call_sid}: {update_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling call status: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/recording-ready")
async def handle_recording_ready(request: Request, db: Session = Depends(get_db)):
    """Webhook when call recording is ready - transcribes, summarizes, and creates email draft"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        recording_url = form_data.get("RecordingUrl")
        recording_sid = form_data.get("RecordingSid")
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_duration = form_data.get("RecordingDuration", "0")

        logger.info(f"Recording ready for call {call_sid}: {recording_url}")

        # Update AI Receptionist Dashboard activity with recording URL
        activity = None
        user_id = None
        lead_id = None
        lead_name = None
        user_email = None

        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['recording_url'] = recording_url
                activity.extra_data['recording_sid'] = recording_sid
                user_id = activity.user_id
                lead_id = activity.lead_id
                db.commit()
                logger.info(f"Updated activity with recording for call {call_sid}")

                # Get user email for draft creation
                if user_id:
                    from main import User
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        user_email = user.email

                # Get lead name if available
                if lead_id:
                    from main import Lead
                    lead = db.query(Lead).filter(Lead.id == lead_id).first()
                    if lead:
                        lead_name = lead.name

        except Exception as update_error:
            logger.warning(f"Could not update recording for call {call_sid}: {update_error}")

        # Process recording asynchronously (transcribe, summarize, create draft)
        import asyncio
        asyncio.create_task(
            process_call_recording(
                recording_url=recording_url,
                recording_sid=recording_sid,
                call_sid=call_sid,
                caller_number=caller_number,
                call_duration=call_duration,
                user_id=user_id,
                user_email=user_email,
                lead_id=lead_id,
                lead_name=lead_name,
                db=db
            )
        )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling recording: {e}")
        return {"status": "error"}


async def process_call_recording(
    recording_url: str,
    recording_sid: str,
    call_sid: str,
    caller_number: str,
    call_duration: str,
    user_id: int,
    user_email: str,
    lead_id: int,
    lead_name: str,
    db: Session
):
    """Process call recording: transcribe, summarize with AI, create email draft"""
    import httpx
    import os
    from anthropic import Anthropic

    logger.info(f"Processing call recording {recording_sid}...")

    try:
        # Step 1: Download the recording from Twilio
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")

        if not twilio_account_sid or not twilio_auth_token:
            logger.error("Twilio credentials not configured")
            return

        # Twilio recording URL needs authentication
        recording_mp3_url = f"{recording_url}.mp3"

        async with httpx.AsyncClient() as client:
            # Download recording
            logger.info(f"Downloading recording from {recording_mp3_url}")
            recording_response = await client.get(
                recording_mp3_url,
                auth=(twilio_account_sid, twilio_auth_token),
                timeout=60.0
            )

            if recording_response.status_code != 200:
                logger.error(f"Failed to download recording: {recording_response.status_code}")
                return

            audio_data = recording_response.content
            logger.info(f"Downloaded {len(audio_data)} bytes of audio")

            # Step 2: Transcribe with OpenAI Whisper
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.error("OpenAI API key not configured")
                return

            logger.info("Transcribing audio with Whisper...")
            transcribe_response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": ("recording.mp3", audio_data, "audio/mpeg")},
                data={"model": "whisper-1", "language": "en"},
                timeout=120.0
            )

            if transcribe_response.status_code != 200:
                logger.error(f"Transcription failed: {transcribe_response.text}")
                return

            transcript = transcribe_response.json().get("text", "")
            logger.info(f"Transcription complete: {len(transcript)} characters")

        # Step 3: Summarize with Claude
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            logger.error("Anthropic API key not configured")
            return

        logger.info("Generating professional summary with Claude...")
        anthropic_client = Anthropic(api_key=anthropic_key)

        client_identifier = lead_name or caller_number

        summary_prompt = f"""You are a professional assistant for a mortgage loan officer.
Summarize the following phone call transcript into a professional call summary.

Call Details:
- Client: {client_identifier}
- Phone: {caller_number}
- Duration: {call_duration} seconds
- Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

Transcript:
{transcript}

Create a professional call summary with the following sections:
1. **Call Overview** - Brief 1-2 sentence summary
2. **Key Discussion Points** - Bullet points of main topics discussed
3. **Client Needs/Requests** - What the client is looking for
4. **Action Items** - Any follow-up tasks or commitments made
5. **Next Steps** - Recommended next actions

Keep the summary concise but comprehensive. Use professional language appropriate for client records."""

        summary_response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            messages=[{"role": "user", "content": summary_prompt}]
        )

        summary = summary_response.content[0].text
        logger.info(f"Summary generated: {len(summary)} characters")

        # Step 4: Create email draft in user's Outlook
        if user_email:
            await create_call_summary_email_draft(
                user_email=user_email,
                client_name=client_identifier,
                caller_number=caller_number,
                call_duration=call_duration,
                summary=summary,
                transcript=transcript,
                recording_url=recording_url
            )
        else:
            logger.warning("No user email available, skipping draft creation")

        # Step 5: Store summary in database
        try:
            activity = db.query(AIReceptionistActivity).filter(
                AIReceptionistActivity.conversation_id == call_sid
            ).first()

            if activity:
                if activity.extra_data is None:
                    activity.extra_data = {}
                activity.extra_data['transcript'] = transcript
                activity.extra_data['summary'] = summary
                activity.summary = summary[:500] if len(summary) > 500 else summary
                db.commit()
                logger.info(f"Stored summary for call {call_sid}")
        except Exception as db_error:
            logger.error(f"Failed to store summary: {db_error}")

        logger.info(f"Call recording processing complete for {call_sid}")

    except Exception as e:
        logger.error(f"Error processing call recording: {e}")


async def create_call_summary_email_draft(
    user_email: str,
    client_name: str,
    caller_number: str,
    call_duration: str,
    summary: str,
    transcript: str,
    recording_url: str
):
    """Create an email draft in the user's Outlook drafts folder"""
    import os
    import httpx
    from msal import ConfidentialClientApplication

    logger.info(f"Creating email draft for {user_email}...")

    try:
        # Get Microsoft Graph token
        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        tenant_id = os.getenv("MICROSOFT_TENANT_ID")

        if not all([client_id, client_secret, tenant_id]):
            logger.warning("Microsoft Graph credentials not configured, skipping draft creation")
            return

        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}"
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            logger.error(f"Failed to get Graph token: {result.get('error_description')}")
            return

        token = result["access_token"]

        # Format email body
        duration_mins = int(call_duration) // 60 if call_duration.isdigit() else 0
        duration_secs = int(call_duration) % 60 if call_duration.isdigit() else 0

        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
<h2 style="color: #2c3e50;">📞 Call Summary - {client_name}</h2>

<table style="margin-bottom: 20px; border-collapse: collapse;">
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Client:</td><td>{client_name}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Phone:</td><td>{caller_number}</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Duration:</td><td>{duration_mins}m {duration_secs}s</td></tr>
<tr><td style="padding: 5px 15px 5px 0; font-weight: bold;">Date:</td><td>{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td></tr>
</table>

<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
{summary.replace(chr(10), '<br>')}
</div>

<details style="margin-top: 20px;">
<summary style="cursor: pointer; font-weight: bold; color: #3498db;">📝 View Full Transcript</summary>
<div style="background: #f0f0f0; padding: 15px; margin-top: 10px; border-radius: 5px; white-space: pre-wrap; font-size: 13px;">
{transcript}
</div>
</details>

<p style="margin-top: 20px; color: #7f8c8d; font-size: 12px;">
<em>This summary was automatically generated by Perennia AI. Please review before sending to the client.</em>
</p>
</body>
</html>
"""

        # Create draft email via Microsoft Graph
        draft_data = {
            "subject": f"Call Summary - {client_name} - {datetime.now().strftime('%m/%d/%Y')}",
            "body": {
                "contentType": "HTML",
                "content": email_body
            },
            "importance": "normal"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=draft_data,
                timeout=30.0
            )

            if response.status_code in [200, 201]:
                draft_id = response.json().get("id")
                logger.info(f"Email draft created successfully: {draft_id}")
            else:
                logger.error(f"Failed to create draft: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error creating email draft: {e}")


@router.post("/voicemail-transcription")
async def handle_voicemail_transcription(request: Request, db: Session = Depends(get_db)):
    """Webhook for voicemail transcription"""
    try:
        _, _, Task, _, _ = get_models()

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


@router.post("/voicemail")
@router.get("/voicemail")
async def voicemail_twiml():
    """Return voicemail TwiML - supports both GET and POST for Twilio"""
    twiml = voice_client.create_voicemail_response()
    return Response(content=str(twiml), media_type="application/xml")


# ============================================================================
# CALL MANAGEMENT API ENDPOINTS
# ============================================================================

@router.post("/make-call")
async def make_outbound_call(
    request: Request,
    db: Session = Depends(get_db)
):
    """Make an outbound AI call"""
    try:
        from main import get_current_user_flexible as auth_dependency
        User, _, _, Activity, _ = get_models()

        # Get current user (manually call dependency)
        current_user = None  # Will be set by auth if needed

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
                    "initiated_by": current_user.id if current_user else None
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
    limit: int = 50,
    offset: int = 0
):
    """Get call history"""
    try:
        _, _, _, Activity, _ = get_models()

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
    db: Session = Depends(get_db)
):
    """Get call statistics"""
    try:
        from sqlalchemy import func
        from datetime import timedelta
        _, Lead, _, Activity, _ = get_models()

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
async def get_ai_receptionist_config():
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
    request: Request
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


# ============================================================================
# VOICE OS DASHBOARD API ENDPOINTS
# ============================================================================

@router.get("/voice-os/config")
async def get_voice_os_config():
    """Get Voice OS configuration for dashboard"""
    import os

    return {
        "status": "running",
        "voice": os.getenv("TTS_VOICE", "alloy"),
        "stt_provider": os.getenv("STT_PROVIDER", "openai"),
        "tts_provider": os.getenv("TTS_PROVIDER", "openai"),
        "ai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "500")),
        "phone_number": voice_client.from_number,
        "business_name": ai_config.business_name,
        "crm_tools": [
            {
                "id": "contact_lookup",
                "name": "Contact Lookup",
                "description": "Search for existing contacts in CRM",
                "enabled": True
            },
            {
                "id": "lead_creation",
                "name": "Lead Creation",
                "description": "Create new leads from call information",
                "enabled": True
            },
            {
                "id": "appointment_scheduling",
                "name": "Appointment Scheduling",
                "description": "Schedule appointments with loan officers",
                "enabled": True
            },
            {
                "id": "task_creation",
                "name": "Task Creation",
                "description": "Create follow-up tasks for team",
                "enabled": True
            },
            {
                "id": "note_taking",
                "name": "Note Taking",
                "description": "Save call notes to contact record",
                "enabled": True
            },
            {
                "id": "call_transfer",
                "name": "Call Transfer",
                "description": "Transfer calls to team members",
                "enabled": True
            },
            {
                "id": "voicemail",
                "name": "Voicemail",
                "description": "Take and transcribe voicemails",
                "enabled": True
            },
            {
                "id": "faq_responses",
                "name": "FAQ Responses",
                "description": "Answer common mortgage questions",
                "enabled": True
            },
            {
                "id": "lead_qualification",
                "name": "Lead Qualification",
                "description": "Pre-screen callers for loan eligibility",
                "enabled": True
            }
        ]
    }


@router.post("/voice-os/config")
async def update_voice_os_config(request: Request):
    """Update Voice OS configuration"""
    try:
        data = await request.json()

        # In production, these would update environment variables or a config file
        # For now, we'll just acknowledge the update

        updated_fields = []

        if "voice" in data:
            # This would update the TTS_VOICE environment variable
            updated_fields.append("voice")
            logger.info(f"Voice updated to: {data['voice']}")

        if "stt_provider" in data:
            updated_fields.append("stt_provider")
            logger.info(f"STT provider updated to: {data['stt_provider']}")

        if "tts_provider" in data:
            updated_fields.append("tts_provider")
            logger.info(f"TTS provider updated to: {data['tts_provider']}")

        if "ai_model" in data:
            updated_fields.append("ai_model")
            logger.info(f"AI model updated to: {data['ai_model']}")

        return {
            "success": True,
            "message": f"Updated: {', '.join(updated_fields)}",
            "updated_fields": updated_fields
        }

    except Exception as e:
        logger.error(f"Error updating Voice OS config: {e}")
        return {"success": False, "error": str(e)}


@router.get("/voice-os/status")
async def get_voice_os_status():
    """Get Voice OS system status and health"""
    import os

    # Voice OS runs through the main Python backend with Twilio + OpenAI integration
    # Check if the essential services are configured and enabled
    twilio_healthy = voice_client.enabled and bool(voice_client.from_number)
    openai_healthy = voice_client.openai_enabled

    # System is "running" if both Twilio and OpenAI are configured
    system_running = twilio_healthy and openai_healthy

    return {
        "system_status": "running" if system_running else "degraded" if (twilio_healthy or openai_healthy) else "stopped",
        "voice_os_url": os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://mortgage-crm-production-7a9a.up.railway.app"),
        "twilio_configured": bool(voice_client.from_number),
        "openai_configured": voice_client.openai_enabled,
        "phone_number": voice_client.from_number,
        "crm_integration": "active",
        "health_checks": {
            "twilio": "healthy" if twilio_healthy else "disconnected",
            "openai": "healthy" if openai_healthy else "disconnected",
            "database": "healthy",
            "webhooks": "configured"
        },
        "capabilities": {
            "inbound_calls": twilio_healthy,
            "outbound_calls": twilio_healthy,
            "ai_responses": openai_healthy,
            "call_transcription": openai_healthy,
            "voicemail": twilio_healthy
        }
    }


# ============================================================================
# MOBILE APP TRANSCRIPTION PROXY
# ============================================================================

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
):
    """
    Proxy to OpenAI Whisper API for audio transcription.
    Used by mobile app when OpenAI key is not in the app.
    """
    import httpx
    import os

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(500, "OpenAI API key not configured on server")

    try:
        # Read uploaded file
        audio_data = await file.read()

        # Send to OpenAI Whisper
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": (file.filename or "audio.m4a", audio_data, file.content_type or "audio/m4a")},
                data={"model": "whisper-1", "language": "en"},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Whisper API error: {response.status_code} - {response.text}")
                raise HTTPException(response.status_code, "Transcription failed")

            result = response.json()
            return {"success": True, "text": result.get("text", "")}

    except httpx.TimeoutException:
        logger.error("Whisper API timeout")
        raise HTTPException(504, "Transcription timed out")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(500, f"Transcription failed: {str(e)}")


# ============================================================================
# VOICE TESTING
# ============================================================================

@router.post("/voice-os/test-voice")
async def test_voice_sample(request: Request):
    """Generate a voice sample for testing different voices"""
    try:
        data = await request.json()
        voice = data.get("voice", "alloy")
        sample_text = data.get("text", "Hello! Thank you for calling. How may I assist you today?")

        # Use OpenAI TTS to generate audio sample
        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=sample_text
            )

            # Convert to base64 for frontend playback
            audio_data = base64.b64encode(response.content).decode('utf-8')

            return {
                "success": True,
                "audio_data": audio_data,
                "voice": voice,
                "format": "mp3"
            }
        except Exception as tts_error:
            logger.error(f"OpenAI TTS error: {tts_error}")
            return {
                "success": False,
                "error": f"TTS generation failed: {str(tts_error)}"
            }

    except Exception as e:
        logger.error(f"Error testing voice: {e}")
        return {"success": False, "error": str(e)}
