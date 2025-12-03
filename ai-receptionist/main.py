"""
===============================================================================
PERENNIA AI RECEPTIONIST - MAIN APPLICATION
===============================================================================
FastAPI application for the AI Receptionist system.

Run with:
    python main.py
    # or
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
===============================================================================
"""

import os
import logging
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import receptionist components
from AI_RECEPTIONIST_PART1_ENGINE import create_engine, ConversationState, CallOutcome
from AI_RECEPTIONIST_PART2_TWILIO import get_voice_client, get_ai_config
from AI_RECEPTIONIST_PART3_AUDIO import create_stt, create_tts, TwilioMediaStreamHandler
from AI_RECEPTIONIST_PART4_INTEGRATION import create_receptionist


# =============================================================================
# APPLICATION SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting AI Receptionist...")

    # Initialize components
    app.state.engine = create_engine(
        company_name=os.getenv("BUSINESS_NAME", "Perennia Mortgage"),
    )
    app.state.voice_client = get_voice_client()
    app.state.ai_config = get_ai_config()
    app.state.receptionist = create_receptionist(
        company_name=os.getenv("BUSINESS_NAME", "Perennia Mortgage"),
        default_lo_id=os.getenv("DEFAULT_LO_ID"),
    )
    app.state.stt = create_stt()
    app.state.tts = create_tts()

    logger.info("AI Receptionist ready!")

    yield

    logger.info("Shutting down AI Receptionist...")


app = FastAPI(
    title="Perennia AI Receptionist",
    description="Intelligent Voice AI for Mortgage Companies",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ai-receptionist",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "engine": "ready",
            "twilio": "configured" if app.state.voice_client else "not configured",
            "stt": "configured" if app.state.stt.config.has_deepgram() else "not configured",
            "tts": "configured" if app.state.tts.config.has_elevenlabs() else "not configured",
        },
    }


# =============================================================================
# TWILIO VOICE WEBHOOKS
# =============================================================================

@app.post("/voice/inbound")
async def handle_inbound_call(request: Request):
    """
    Handle incoming calls from Twilio.

    Returns TwiML to greet caller and gather speech input.
    """
    form_data = await request.form()
    caller_phone = form_data.get("From", "Unknown")
    call_sid = form_data.get("CallSid", "")

    logger.info(f"Incoming call from {caller_phone} (SID: {call_sid})")

    # Start conversation
    caller_info = app.state.receptionist.lookup_caller(caller_phone)
    state = app.state.engine.start_conversation(
        call_sid=call_sid,
        caller_phone=caller_phone,
        caller_info=caller_info.get("data") if caller_info.get("status") == "success" else None,
    )

    # Log to CRM
    app.state.receptionist.log_interaction(
        call_sid=call_sid,
        caller_phone=caller_phone,
        interaction_type="incoming_call",
    )

    # Generate greeting
    twiml = app.state.voice_client.create_greeting_response(
        company_name=app.state.ai_config.business_name,
    )

    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/process-speech")
async def process_speech(request: Request):
    """
    Process speech input from caller.

    Twilio sends the transcribed speech here after gathering.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    speech_result = form_data.get("SpeechResult", "")
    confidence = float(form_data.get("Confidence", 0))

    logger.info(f"Speech from {call_sid}: {speech_result} (confidence: {confidence})")

    if not speech_result:
        # No speech detected
        twiml = app.state.voice_client.create_say_response(
            "I didn't catch that. Could you please repeat?",
            gather_after=True,
        )
        return Response(content=twiml, media_type="application/xml")

    # Process with AI engine
    result = await app.state.engine.process_speech(call_sid, speech_result)

    # Check if transfer needed
    if result.get("needs_transfer"):
        # Get routing recommendation
        routing = app.state.receptionist.route_call(
            caller_phone="",  # Get from state
            intent=result.get("intent", "unknown"),
            urgency="normal",
        )

        transfer_to = os.getenv("TRANSFER_NUMBER", "+15551234567")
        twiml = app.state.voice_client.create_transfer_response(
            transfer_to=transfer_to,
            announcement=result.get("response"),
        )
        return Response(content=twiml, media_type="application/xml")

    # Generate response TwiML
    ai_response = result.get("response", "I'm sorry, I didn't understand. Can you repeat that?")
    twiml = app.state.voice_client.create_say_response(
        ai_response,
        gather_after=True,
    )

    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/transfer")
async def handle_transfer(request: Request):
    """Handle transfer to human agent."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")

    logger.info(f"Transferring call {call_sid}")

    transfer_to = os.getenv("TRANSFER_NUMBER", "+15551234567")
    twiml = app.state.voice_client.create_transfer_response(
        transfer_to=transfer_to,
        announcement="Please hold while I transfer you to a loan officer.",
    )

    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/status")
async def handle_status_callback(request: Request):
    """Handle Twilio status callbacks."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", 0)

    logger.info(f"Call {call_sid} status: {call_status}, duration: {duration}s")

    # End conversation if completed
    if call_status in ["completed", "busy", "failed", "no-answer"]:
        outcome = {
            "completed": CallOutcome.COMPLETED,
            "busy": CallOutcome.ABANDONED,
            "failed": CallOutcome.ABANDONED,
            "no-answer": CallOutcome.ABANDONED,
        }.get(call_status, CallOutcome.COMPLETED)

        summary = app.state.engine.end_conversation(call_sid, outcome)

        if summary:
            # Log to CRM
            app.state.receptionist.log_interaction(
                call_sid=call_sid,
                caller_phone=summary.get("caller_phone", ""),
                interaction_type="call_completed",
                outcome=outcome.value,
                transcript=str(summary.get("transcript", [])),
            )

    return JSONResponse({"status": "ok"})


@app.post("/voice/voicemail-complete")
async def handle_voicemail(request: Request):
    """Handle voicemail recording completion."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    recording_url = form_data.get("RecordingUrl", "")
    recording_duration = form_data.get("RecordingDuration", 0)

    logger.info(f"Voicemail received for {call_sid}: {recording_url}")

    # Log voicemail
    app.state.receptionist.log_interaction(
        call_sid=call_sid,
        caller_phone="",
        interaction_type="voicemail",
        notes=f"Recording: {recording_url}, Duration: {recording_duration}s",
    )

    twiml = app.state.voice_client.create_say_response(
        "Thank you for your message. A loan officer will call you back shortly. Goodbye.",
        end_call=True,
    )

    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# WEBSOCKET FOR AUDIO STREAMING
# =============================================================================

@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """
    WebSocket endpoint for bidirectional audio streaming.

    Used with Twilio Media Streams for real-time audio processing.
    """
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    handler = TwilioMediaStreamHandler(
        stt=app.state.stt,
        tts=app.state.tts,
    )

    try:
        while True:
            data = await websocket.receive_json()
            result = await handler.handle_message(data)

            if result and result.get("transcript"):
                # Process transcript with AI
                transcript = result["transcript"]
                logger.info(f"Transcript: {transcript}")

                # Generate AI response
                # This would integrate with the conversation engine

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"Voice stream error: {e}")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.post("/api/outbound-call")
async def initiate_outbound_call(
    to: str = Form(...),
    purpose: str = Form("follow_up"),
):
    """Initiate an outbound call."""
    result = app.state.voice_client.make_call(to=to)

    if result.get("error"):
        return JSONResponse(
            {"status": "error", "error": result["error"]},
            status_code=400,
        )

    return JSONResponse({
        "status": "success",
        "call_sid": result.get("call_sid"),
    })


@app.get("/api/call/{call_sid}")
async def get_call_details(call_sid: str):
    """Get call details."""
    result = app.state.voice_client.get_call(call_sid)
    return JSONResponse(result)


@app.post("/api/callback")
async def create_callback_request(
    phone: str = Form(...),
    name: Optional[str] = Form(None),
    preferred_time: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
):
    """Create a callback request."""
    result = app.state.receptionist.create_callback(
        caller_phone=phone,
        caller_name=name,
        preferred_time=preferred_time,
        reason=reason,
    )

    return JSONResponse(result)


@app.get("/api/availability")
async def check_availability(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Check available appointment slots."""
    result = app.state.receptionist.check_availability(
        date_from=date_from,
        date_to=date_to,
    )

    return JSONResponse(result)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
