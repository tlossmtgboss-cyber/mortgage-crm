"""
================================================================================
PERENNIA AI RECEPTIONIST - MAIN APPLICATION
================================================================================
FastAPI application entry point with Telnyx webhook and WebSocket endpoints.
================================================================================
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_db():
    """Database session context manager.

    WARNING: This is a standalone deployment package with its own engine.
    RLS tenant context is NOT set because this runs outside the main app.
    The AI receptionist uses organization-scoped queries explicitly.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import AI Receptionist components
AI_RECEPTIONIST_AVAILABLE = False
AIReceptionist = None  # Placeholder for type when import fails
create_receptionist = None
create_audio_processor = None
handle_voice_stream_websocket = None

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

# Global receptionist instance (type annotation as string to avoid issues)
receptionist = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global receptionist

    logger.info("Starting Perennia AI Receptionist...")

    if AI_RECEPTIONIST_AVAILABLE:
        receptionist = create_receptionist(
            company_name=os.getenv("COMPANY_NAME", "The Tim Loss Team"),
            receptionist_name=os.getenv("RECEPTIONIST_NAME", "Aria"),
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
_ALLOWED_ORIGINS = [
    origin for origin in [
        os.getenv("FRONTEND_URL", "https://app.perenniaai.com"),
        os.getenv("API_URL", "https://api.perenniaai.com"),
    ] if origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
# TELNYX VOICE WEBHOOKS
# =============================================================================

class TelnyxVoiceRequest(BaseModel):
    """Telnyx voice webhook request."""
    CallSid: str
    From: str
    To: str
    CallStatus: Optional[str] = None
    Direction: Optional[str] = None


@app.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming voice call from Telnyx."""
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
    """Handle call status updates from Telnyx."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")

    logger.info(f"Call status update: {call_sid} -> {call_status}")

    # Update call log in database
    try:
        with get_db() as db:
            # Map Telnyx status to our status
            ended_statuses = ["completed", "busy", "failed", "no-answer", "canceled"]
            update_data = {"status": call_status}

            if call_status in ended_statuses:
                update_data["ended_at"] = datetime.now(timezone.utc)
                # Get duration if available
                duration = form_data.get("CallDuration")
                if duration:
                    update_data["duration_seconds"] = int(duration)

            db.execute(
                text("""
                    UPDATE call_logs
                    SET status = :status,
                        ended_at = COALESCE(:ended_at, ended_at),
                        duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE call_sid = :call_sid
                """),
                {
                    "call_sid": call_sid,
                    "status": call_status,
                    "ended_at": update_data.get("ended_at"),
                    "duration_seconds": update_data.get("duration_seconds"),
                }
            )
            db.commit()
            logger.info(f"Updated call log for {call_sid}")
    except Exception as e:
        logger.error(f"Failed to update call log: {e}")

    return {"status": "received"}


# =============================================================================
# WEBSOCKET MEDIA STREAM
# =============================================================================

@app.websocket("/voice/stream/{call_sid}")
async def voice_stream(websocket: WebSocket, call_sid: str):
    """Handle Telnyx Media Stream WebSocket connection."""
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
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT id, call_sid, from_number, to_number, direction,
                           status, started_at, ended_at, duration_seconds,
                           outcome, notes, created_at
                    FROM call_logs
                    ORDER BY started_at DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            )
            calls = [dict(row._mapping) for row in result.fetchall()]

            # Get total count
            count_result = db.execute(text("SELECT COUNT(*) FROM call_logs"))
            total = count_result.scalar()

            return {
                "calls": [
                    {
                        **call,
                        "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
                        "ended_at": call["ended_at"].isoformat() if call.get("ended_at") else None,
                        "created_at": call["created_at"].isoformat() if call.get("created_at") else None,
                    }
                    for call in calls
                ],
                "total": total
            }
    except Exception as e:
        logger.error(f"Failed to get recent calls: {e}")
        return {"calls": [], "total": 0, "error": "Internal server error"}


@app.get("/api/calls/{call_sid}")
async def get_call_details(call_sid: str):
    """Get details for a specific call."""
    try:
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT id, call_sid, from_number, to_number, direction,
                           status, started_at, ended_at, duration_seconds,
                           recording_url, transcript, sentiment_score,
                           caller_id, loan_officer_id, transferred_to,
                           transfer_reason, outcome, notes, metadata,
                           created_at, updated_at
                    FROM call_logs
                    WHERE call_sid = :call_sid
                """),
                {"call_sid": call_sid}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Call not found")

            call = dict(row._mapping)

            # Get call events
            events_result = db.execute(
                text("""
                    SELECT event_type, event_data, timestamp
                    FROM call_events
                    WHERE call_log_id = :call_id
                    ORDER BY timestamp ASC
                """),
                {"call_id": call["id"]}
            )
            events = [dict(e._mapping) for e in events_result.fetchall()]

            return {
                **call,
                "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
                "ended_at": call["ended_at"].isoformat() if call.get("ended_at") else None,
                "created_at": call["created_at"].isoformat() if call.get("created_at") else None,
                "updated_at": call["updated_at"].isoformat() if call.get("updated_at") else None,
                "events": [
                    {
                        **event,
                        "timestamp": event["timestamp"].isoformat() if event.get("timestamp") else None,
                    }
                    for event in events
                ],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/callbacks")
async def get_pending_callbacks():
    """Get pending callback requests."""
    try:
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT cr.id, cr.call_log_id, cr.caller_name, cr.caller_phone,
                           cr.reason, cr.urgency, cr.assigned_to, cr.status,
                           cr.scheduled_at, cr.notes, cr.created_at,
                           cl.call_sid, cl.from_number
                    FROM callback_requests cr
                    LEFT JOIN call_logs cl ON cl.id = cr.call_log_id
                    WHERE cr.status = 'pending'
                    ORDER BY
                        CASE cr.urgency
                            WHEN 'urgent' THEN 1
                            WHEN 'high' THEN 2
                            WHEN 'normal' THEN 3
                            WHEN 'low' THEN 4
                            ELSE 5
                        END,
                        cr.created_at ASC
                """)
            )
            callbacks = [dict(row._mapping) for row in result.fetchall()]

            # Get total count of pending callbacks
            count_result = db.execute(
                text("SELECT COUNT(*) FROM callback_requests WHERE status = 'pending'")
            )
            total = count_result.scalar()

            return {
                "callbacks": [
                    {
                        **cb,
                        "scheduled_at": cb["scheduled_at"].isoformat() if cb.get("scheduled_at") else None,
                        "created_at": cb["created_at"].isoformat() if cb.get("created_at") else None,
                    }
                    for cb in callbacks
                ],
                "total": total
            }
    except Exception as e:
        logger.error(f"Failed to get pending callbacks: {e}")
        return {"callbacks": [], "total": 0, "error": "Internal server error"}


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
