"""
Voice Routes - Telnyx WebSocket for AI Receptionist Calls

Contains:
- /ws/voice-stream WebSocket endpoint (Telnyx Media Streams -> OpenAI Realtime)
- save_call_summary helper
"""
import os
import logging
import json
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistError,
    AIReceptionistConversation
)
from services.voice_sentiment_service import analyze_voice_sentiment

from .openai_realtime import connect_to_openai_realtime, extract_lead_info
from .tool_handlers import handle_ai_function_call
from .utils import get_models, voice_client, ai_config

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WEBSOCKET FOR OPENAI REALTIME API (Telnyx)
# ============================================================================

@router.websocket("/ws/voice-stream")
async def voice_stream_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for Telnyx Media Streams -> OpenAI Realtime API
    Handles bidirectional audio streaming for AI conversations
    """
    logger.info(f"WebSocket connection attempt from: {websocket.client}")
    logger.info(f"Headers: {dict(websocket.headers)}")

    # --- CRIT-3: Use proper session construction instead of get_db().__next__() ---
    from db import SessionLocal
    db = SessionLocal()

    try:
        await websocket.accept()
        logger.info("Voice stream WebSocket connected successfully!")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        db.close()
        raise

    # Store call context
    call_context = {
        "call_sid": None,
        "caller_number": None,
        "caller_name": None,      # Known caller's name from CRM
        "caller_category": None,  # client, realtor, etc.
        "conversation_history": [],
        "lead_data": {},
        "intent": None,
        "session_ready": False,  # OpenAI session configured
        "stream_ready": False,   # Telnyx stream started
        "greeting_sent": False   # Greeting already triggered
    }

    openai_ws = None
    try:
        # Connect to OpenAI Realtime API with timeout
        try:
            openai_ws = await connect_to_openai_realtime()
            logger.info("OpenAI Realtime API connected successfully")
        except asyncio.TimeoutError:
            logger.error("OpenAI Realtime connection timed out")
            await websocket.close(code=1011, reason="AI service timeout")
            return
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime: {e}")
            await websocket.close(code=1011, reason=f"AI service error: {str(e)[:50]}")
            return

        # Helper to trigger greeting only when BOTH conditions are met
        async def maybe_trigger_greeting():
            """Trigger AI greeting only when OpenAI session is ready AND Telnyx stream has started"""
            if call_context['session_ready'] and call_context['stream_ready'] and not call_context['greeting_sent']:
                call_context['greeting_sent'] = True
                logger.info("Both OpenAI session and Telnyx stream ready - triggering AI greeting")
                try:
                    # Build personalized greeting based on caller info
                    caller_name = call_context.get('caller_name')
                    caller_category = call_context.get('caller_category')

                    if caller_name:
                        # Extract first name for friendlier greeting
                        first_name = caller_name.split()[0] if caller_name else caller_name

                        # Known caller - personalized greeting based on category
                        if caller_category == 'client':
                            greeting = f"Hi {first_name}! This is Aria with CMG Home Loans. Great to hear from you! How can I help you today?"
                        elif caller_category == 'lead':
                            greeting = f"Hi {first_name}! This is Aria with CMG Home Loans. Thanks for calling! How can I help you today?"
                        elif caller_category == 'team':
                            greeting = f"Hey {first_name}! This is Aria. What can I do for you?"
                        elif caller_category == 'realtor':
                            greeting = f"Hi {first_name}! This is Aria with CMG Home Loans. Thanks for calling! How can I help you today?"
                        else:
                            greeting = f"Hi {first_name}! This is Aria with CMG Home Loans. Thanks for calling. How can I help you today?"
                        logger.info(f"Using personalized greeting ({caller_category})")
                    else:
                        # Unknown caller - generic greeting
                        greeting = "Hi, this is Aria with CMG Home Loans! Thanks for calling. How can I help you today?"
                        logger.info("Using generic greeting for unknown caller")

                    # Request a response with the greeting
                    await openai_ws.send(json.dumps({
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": f"Greet the caller warmly. Say exactly: {greeting}"
                        }
                    }))
                    logger.info("Greeting response requested with instructions")
                except Exception as greet_err:
                    logger.error(f"Failed to trigger greeting: {greet_err}")

        # Handle bidirectional streaming
        async def telnyx_to_openai():
            """Forward audio from Telnyx to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data['event'] == 'start':
                        call_context['call_sid'] = data['start']['callSid']
                        call_context['stream_sid'] = data['start']['streamSid']  # Capture stream SID

                        # Extract caller info from custom parameters
                        custom_params = data['start'].get('customParameters', {})
                        call_context['caller_number'] = custom_params.get('caller_phone') or custom_params.get('From')
                        call_context['caller_name'] = custom_params.get('caller_name')
                        call_context['caller_category'] = custom_params.get('caller_category')

                        logger.info(f"Call started: {call_context['call_sid']}, stream: {call_context['stream_sid']}")
                        logger.info(f"Caller identified, Category: {call_context['caller_category']}")

                        # Mark Telnyx stream as ready, try to trigger greeting
                        call_context['stream_ready'] = True
                        logger.info(f"Telnyx stream ready. Session ready: {call_context['session_ready']}")
                        await maybe_trigger_greeting()

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
                logger.error(f"Error in Telnyx->OpenAI stream: {e}")

        async def openai_to_telnyx():
            """Forward AI responses from OpenAI to Telnyx"""
            try:
                async for message in openai_ws:
                    data = json.loads(message)
                    event_type = data.get('type', 'unknown')

                    # Log all events for debugging
                    if event_type not in ['response.audio.delta', 'input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped']:
                        logger.info(f"OpenAI event: {event_type}")

                    # Handle session.updated - OpenAI is now configured
                    if event_type == 'session.updated':
                        call_context['session_ready'] = True
                        logger.info(f"OpenAI session configured. Telnyx stream ready: {call_context['stream_ready']}")
                        await maybe_trigger_greeting()

                    if event_type == 'response.audio.delta':
                        # Forward AI audio to Telnyx
                        audio_payload = data.get('delta', '')
                        if audio_payload and call_context.get('stream_sid'):
                            try:
                                await websocket.send_json({
                                    "event": "media",
                                    "streamSid": call_context['stream_sid'],
                                    "media": {
                                        "payload": audio_payload
                                    }
                                })
                            except Exception as send_err:
                                logger.error(f"Failed to send audio to Telnyx: {send_err}")
                        else:
                            logger.warning(f"Missing audio payload ({len(audio_payload) if audio_payload else 0} bytes) or stream_sid ({call_context.get('stream_sid')})")

                    elif event_type == 'response.audio.done':
                        logger.info("OpenAI audio response complete")

                    elif event_type == 'response.done':
                        # Log the full response for debugging
                        response_data = data.get('response', {})
                        output_items = response_data.get('output', [])
                        status = response_data.get('status', 'unknown')
                        logger.info(f"OpenAI response done - status: {status}, output items: {len(output_items)}")
                        if not output_items:
                            logger.warning(f"Empty response from OpenAI! Full data: {json.dumps(data)[:500]}")

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

                    elif event_type == 'response.function_call_arguments.done':
                        # Handle function calls from the AI
                        func_name = data.get('name', '')
                        func_args = data.get('arguments', '{}')
                        call_id = data.get('call_id', '')

                        logger.info(f"Function call: {func_name} with args: {func_args}")

                        try:
                            args = json.loads(func_args)

                            # --- HIGH-1: Validate function call arguments ---
                            if not isinstance(args, dict):
                                raise ValueError("Function arguments must be a JSON object")
                            for key, val in args.items():
                                if isinstance(val, str) and len(val) > 2000:
                                    raise ValueError(f"Argument '{key}' exceeds max length (2000 chars)")
                                if not isinstance(key, str) or len(key) > 100:
                                    raise ValueError(f"Invalid argument key: {str(key)[:50]}")

                            result = await handle_ai_function_call(
                                func_name, args, call_context, db
                            )

                            # Send function result back to OpenAI
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": json.dumps(result)
                                }
                            }))

                            # Request AI to continue responding after function result
                            await openai_ws.send(json.dumps({
                                "type": "response.create"
                            }))

                            logger.info(f"Function {func_name} completed: {result}")

                        except Exception as func_err:
                            logger.error(f"Function call error: {func_err}")

            except Exception as e:
                logger.error(f"Error in OpenAI->Telnyx stream: {e}")

        # Run both streams concurrently
        await asyncio.gather(
            telnyx_to_openai(),
            openai_to_telnyx()
        )

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in voice stream: {e}")
    finally:
        try:
            await websocket.close()
        except Exception as e:
            logger.error(f"Error in voice_stream (close websocket): {e}")
            pass  # WebSocket may already be closed
        try:
            if openai_ws:
                await openai_ws.close()
        except Exception as e:
            logger.error(f"Error in voice_stream (close openai_ws): {e}")
            pass  # OpenAI WebSocket may already be closed
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error in voice_stream (close db session): {e}")
            pass  # Session may already be closed
        logger.info("Voice stream cleanup complete")


# ============================================================================
# CALL SUMMARY
# ============================================================================

async def save_call_summary(call_context: dict, db: Session):
    """Save call summary and create lead/task if needed"""
    try:
        _, Lead, _, Activity, _ = get_models()

        # Create or update lead
        if call_context['lead_data'].get('phone'):
            phone = call_context['lead_data']['phone']

            # TENANT-001: Scope phone lookup by organization.
            # Derive org_id from the call context or the Telnyx phone number config.
            org_id = call_context.get('organization_id')

            # Check if lead exists
            phone_query = db.query(Lead).filter(Lead.phone == phone)
            if org_id:
                phone_query = phone_query.filter(Lead.organization_id == org_id)
            lead = phone_query.first()

            if not lead:
                # Create new lead — include organization_id for tenant isolation
                lead = Lead(
                    name=call_context['lead_data'].get('name', 'Phone Inquiry'),
                    phone=phone,
                    source="Phone Call",
                    stage="NEW",
                    organization_id=org_id,
                    notes=f"Inbound call. Conversation summary:\n{json.dumps(call_context['conversation_history'], indent=2)}"
                )
                db.add(lead)
                logger.info("Created new lead from call")

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

            # Save full conversation to dashboard
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
                sentiment=analyze_voice_sentiment(call_context['conversation_history']),
                outcome=call_context.get('outcome', 'completed'),
                avg_confidence_score=call_context.get('avg_confidence', 0.85),
                total_turns=len(call_context['conversation_history']),
                extra_data={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data']
                }
            )
            db.add(conversation_record)

            # Update activity feed with conversation summary
            activity_update = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                action_type='conversation_summary',
                channel='voice',
                confidence_score=call_context.get('avg_confidence', 0.85),
                ai_version=os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-12-17'),
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
            logger.info("Saved call summary")

    except Exception as e:
        logger.error(f"Error saving call summary: {e}")
        db.rollback()

        # Log error to dashboard
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
        except Exception as e:
            logger.error(f"Error in save_call_summary (error logging): {e}")
            pass  # Don't fail on error logging
