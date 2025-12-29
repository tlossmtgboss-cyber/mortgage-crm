"""
================================================================================
PERENNIA AI RECEPTIONIST - MAIN APPLICATION
================================================================================
FastAPI application entry point with Twilio webhook and WebSocket endpoints.
================================================================================
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import AI Receptionist components
try:
    from ai_receptionist import (
        create_receptionist,
        create_audio_processor,
        handle_voice_stream_websocket,
        AIReceptionist,
    )
    AI_RECEPTIONIST_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AI Receptionist module not available: {e}")
    AI_RECEPTIONIST_AVAILABLE = False

# Global receptionist instance
receptionist: Optional[AIReceptionist] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global receptionist

    logger.info("Starting Perennia AI Receptionist...")

    if AI_RECEPTIONIST_AVAILABLE:
        receptionist = create_receptionist(
            company_name=os.getenv("COMPANY_NAME", "Perennia Mortgage"),
            receptionist_name=os.getenv("RECEPTIONIST_NAME", "Sarah"),
        )
        logger.info("AI Receptionist initialized")

    yield

    logger.info("Shutting down Perennia AI Receptionist...")
    if receptionist:
        # Cleanup if needed
        pass


# Create FastAPI app
app = FastAPI(
    title="Perennia AI Receptionist",
    description="AI-powered voice receptionist for mortgage companies",
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
        "service": "perennia-ai-receptionist",
        "timestamp": datetime.utcnow().isoformat(),
        "ai_receptionist_available": AI_RECEPTIONIST_AVAILABLE,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Perennia AI Receptionist",
        "version": "1.0.0",
        "status": "running",
    }


# =============================================================================
# TWILIO VOICE WEBHOOKS
# =============================================================================

class TwilioVoiceRequest(BaseModel):
    """Twilio voice webhook request."""
    CallSid: str
    From: str
    To: str
    CallStatus: Optional[str] = None
    Direction: Optional[str] = None


@app.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming voice call from Twilio."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")

    logger.info(f"Incoming call: {call_sid} from {from_number}")

    # Get WebSocket URL for media stream
    host = request.headers.get("host", "localhost:8000")
    ws_url = f"wss://{host}/voice/stream/{call_sid}"

    # Generate TwiML response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="CallSid" value="{call_sid}"/>
            <Parameter name="From" value="{from_number}"/>
            <Parameter name="To" value="{to_number}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/status")
async def handle_call_status(request: Request):
    """Handle call status updates from Twilio."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    call_duration = form_data.get("CallDuration")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    direction = form_data.get("Direction")
    timestamp = form_data.get("Timestamp")

    logger.info(f"Call status update: {call_sid} -> {call_status}")

    # Update call log in database
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        database_url = os.getenv("DATABASE_URL")
        if database_url:
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)

            engine = create_engine(database_url)
            Session = sessionmaker(bind=engine)
            db = Session()

            try:
                # Check if call log exists
                existing = db.execute(text("""
                    SELECT id FROM ai_receptionist_call_logs WHERE call_sid = :call_sid
                """), {"call_sid": call_sid}).fetchone()

                if existing:
                    # Update existing record
                    db.execute(text("""
                        UPDATE ai_receptionist_call_logs
                        SET status = :status,
                            duration_seconds = :duration,
                            updated_at = NOW()
                        WHERE call_sid = :call_sid
                    """), {
                        "call_sid": call_sid,
                        "status": call_status,
                        "duration": int(call_duration) if call_duration else None,
                    })
                else:
                    # Insert new record
                    db.execute(text("""
                        INSERT INTO ai_receptionist_call_logs (
                            call_sid, status, from_number, to_number,
                            direction, duration_seconds, created_at, updated_at
                        ) VALUES (
                            :call_sid, :status, :from_number, :to_number,
                            :direction, :duration, NOW(), NOW()
                        )
                    """), {
                        "call_sid": call_sid,
                        "status": call_status,
                        "from_number": from_number,
                        "to_number": to_number,
                        "direction": direction,
                        "duration": int(call_duration) if call_duration else None,
                    })

                db.commit()
                logger.info(f"Updated call log for {call_sid}")
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Failed to update call log: {e}")

    return {"status": "received"}


# =============================================================================
# WEBSOCKET MEDIA STREAM
# =============================================================================

@app.websocket("/voice/stream/{call_sid}")
async def voice_stream(websocket: WebSocket, call_sid: str):
    """Handle Twilio Media Stream WebSocket connection."""
    await websocket.accept()
    logger.info(f"WebSocket connected for call: {call_sid}")

    try:
        if AI_RECEPTIONIST_AVAILABLE:
            async with create_audio_processor() as processor:
                await handle_voice_stream_websocket(
                    websocket=websocket,
                    audio_processor=processor,
                    receptionist=receptionist,
                )
        else:
            # Fallback: just acknowledge messages
            while True:
                data = await websocket.receive_text()
                # Echo acknowledgment

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call: {call_sid}")
    except Exception as e:
        logger.error(f"WebSocket error for call {call_sid}: {e}")
    finally:
        logger.info(f"WebSocket session ended for call: {call_sid}")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/api/calls")
async def get_recent_calls(limit: int = 20):
    """Get recent call logs."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return {"calls": [], "total": 0, "message": "Database not configured"}

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            # Get recent calls
            result = db.execute(text("""
                SELECT
                    id, call_sid, status, from_number, to_number,
                    direction, duration_seconds, transcript,
                    callback_requested, callback_reason,
                    created_at, updated_at
                FROM ai_receptionist_call_logs
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": limit}).fetchall()

            # Get total count
            total = db.execute(text("""
                SELECT COUNT(*) FROM ai_receptionist_call_logs
            """)).scalar()

            calls = []
            for row in result:
                calls.append({
                    "id": row.id,
                    "call_sid": row.call_sid,
                    "status": row.status,
                    "from_number": row.from_number,
                    "to_number": row.to_number,
                    "direction": row.direction,
                    "duration_seconds": row.duration_seconds,
                    "transcript": row.transcript,
                    "callback_requested": row.callback_requested,
                    "callback_reason": row.callback_reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                })

            return {"calls": calls, "total": total or 0}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to get calls: {e}")
        return {"calls": [], "total": 0, "error": str(e)}


@app.get("/api/calls/{call_sid}")
async def get_call_details(call_sid: str):
    """Get details for a specific call."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return {"call_sid": call_sid, "status": "not_found", "message": "Database not configured"}

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            result = db.execute(text("""
                SELECT
                    id, call_sid, status, from_number, to_number,
                    direction, duration_seconds, transcript,
                    callback_requested, callback_reason,
                    intent_detected, sentiment, summary,
                    created_at, updated_at
                FROM ai_receptionist_call_logs
                WHERE call_sid = :call_sid
            """), {"call_sid": call_sid}).fetchone()

            if not result:
                return {"call_sid": call_sid, "status": "not_found"}

            return {
                "id": result.id,
                "call_sid": result.call_sid,
                "status": result.status,
                "from_number": result.from_number,
                "to_number": result.to_number,
                "direction": result.direction,
                "duration_seconds": result.duration_seconds,
                "transcript": result.transcript,
                "callback_requested": result.callback_requested,
                "callback_reason": result.callback_reason,
                "intent_detected": result.intent_detected,
                "sentiment": result.sentiment,
                "summary": result.summary,
                "created_at": result.created_at.isoformat() if result.created_at else None,
                "updated_at": result.updated_at.isoformat() if result.updated_at else None,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to get call details: {e}")
        return {"call_sid": call_sid, "status": "error", "error": str(e)}


@app.get("/api/callbacks")
async def get_pending_callbacks():
    """Get pending callback requests."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return {"callbacks": [], "total": 0, "message": "Database not configured"}

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            # Get callbacks where callback was requested
            result = db.execute(text("""
                SELECT
                    id, call_sid, from_number, callback_reason,
                    intent_detected, summary, created_at
                FROM ai_receptionist_call_logs
                WHERE callback_requested = true
                ORDER BY created_at DESC
            """)).fetchall()

            callbacks = []
            for row in result:
                callbacks.append({
                    "id": row.id,
                    "call_sid": row.call_sid,
                    "phone_number": row.from_number,
                    "reason": row.callback_reason,
                    "intent": row.intent_detected,
                    "summary": row.summary,
                    "requested_at": row.created_at.isoformat() if row.created_at else None,
                })

            return {"callbacks": callbacks, "total": len(callbacks)}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to get callbacks: {e}")
        return {"callbacks": [], "total": 0, "error": str(e)}


@app.get("/api/metrics")
async def get_metrics():
    """Get receptionist metrics."""
    if receptionist:
        return receptionist.get_metrics()
    return {"status": "receptionist_not_available"}


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
