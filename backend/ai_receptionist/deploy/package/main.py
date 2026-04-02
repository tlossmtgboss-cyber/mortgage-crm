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
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

# Load environment variables
load_dotenv()

# =============================================================================
# DATABASE SETUP
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
# Fix postgres:// to postgresql:// for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=3,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Database session dependency."""
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

    # Create call log in database
    try:
        db = SessionLocal()
        db.execute(
            text("""
                INSERT INTO call_logs (call_sid, from_number, to_number, direction, status, started_at)
                VALUES (:call_sid, :from_number, :to_number, 'inbound', 'initiated', CURRENT_TIMESTAMP)
                ON CONFLICT (call_sid) DO UPDATE SET
                    status = 'initiated',
                    updated_at = CURRENT_TIMESTAMP
            """),
            {"call_sid": call_sid, "from_number": from_number, "to_number": to_number}
        )
        db.commit()
        db.close()
        logger.info(f"Call log created for {call_sid}")
    except Exception as e:
        logger.error(f"Failed to create call log: {e}")

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
    call_duration = form_data.get("CallDuration")

    logger.info(f"Call status update: {call_sid} -> {call_status}")

    # Update call log in database
    try:
        db = SessionLocal()

        # Build update query based on status
        if call_status in ("completed", "busy", "no-answer", "failed", "canceled"):
            # Call ended - update with end time and duration
            db.execute(
                text("""
                    UPDATE call_logs
                    SET status = :status,
                        ended_at = CURRENT_TIMESTAMP,
                        duration_seconds = :duration,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE call_sid = :call_sid
                """),
                {
                    "call_sid": call_sid,
                    "status": call_status,
                    "duration": int(call_duration) if call_duration else None
                }
            )
        else:
            # Status update (ringing, in-progress, etc.)
            db.execute(
                text("""
                    UPDATE call_logs
                    SET status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE call_sid = :call_sid
                """),
                {"call_sid": call_sid, "status": call_status}
            )

        db.commit()
        db.close()
        logger.info(f"Call log updated for {call_sid}: {call_status}")
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
async def get_recent_calls(limit: int = 20, offset: int = 0):
    """Get recent call logs."""
    try:
        db = SessionLocal()

        # Get total count
        count_result = db.execute(text("SELECT COUNT(*) FROM call_logs"))
        total = count_result.scalar() or 0

        # Get recent calls
        result = db.execute(
            text("""
                SELECT
                    id, call_sid, from_number, to_number, direction, status,
                    started_at, ended_at, duration_seconds, recording_url,
                    transcript, sentiment_score, outcome, notes, created_at
                FROM call_logs
                ORDER BY started_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset}
        )
        rows = result.fetchall()
        columns = result.keys()
        db.close()

        calls = []
        for row in rows:
            call_dict = dict(zip(columns, row))
            # Convert datetime objects to ISO strings
            for key in ["started_at", "ended_at", "created_at"]:
                if call_dict.get(key):
                    call_dict[key] = call_dict[key].isoformat()
            # Convert Decimal to float for sentiment_score
            if call_dict.get("sentiment_score"):
                call_dict["sentiment_score"] = float(call_dict["sentiment_score"])
            calls.append(call_dict)

        return {"calls": calls, "total": total, "limit": limit, "offset": offset}

    except Exception as e:
        logger.error(f"Failed to get recent calls: {e}")
        return {"calls": [], "total": 0, "error": "Internal server error"}


@app.get("/api/calls/{call_sid}")
async def get_call_details(call_sid: str):
    """Get details for a specific call."""
    try:
        db = SessionLocal()

        # Get call details
        result = db.execute(
            text("""
                SELECT
                    cl.id, cl.call_sid, cl.from_number, cl.to_number, cl.direction,
                    cl.status, cl.started_at, cl.ended_at, cl.duration_seconds,
                    cl.recording_url, cl.transcript, cl.sentiment_score,
                    cl.outcome, cl.notes, cl.metadata, cl.created_at, cl.updated_at
                FROM call_logs cl
                WHERE cl.call_sid = :call_sid
            """),
            {"call_sid": call_sid}
        )
        row = result.fetchone()

        if not row:
            db.close()
            raise HTTPException(status_code=404, detail=f"Call {call_sid} not found")

        columns = result.keys()
        call_dict = dict(zip(columns, row))

        # Convert datetime objects to ISO strings
        for key in ["started_at", "ended_at", "created_at", "updated_at"]:
            if call_dict.get(key):
                call_dict[key] = call_dict[key].isoformat()

        # Convert Decimal to float for sentiment_score
        if call_dict.get("sentiment_score"):
            call_dict["sentiment_score"] = float(call_dict["sentiment_score"])

        # Get call events
        events_result = db.execute(
            text("""
                SELECT id, event_type, event_data, timestamp
                FROM call_events
                WHERE call_log_id = :call_log_id
                ORDER BY timestamp ASC
            """),
            {"call_log_id": call_dict["id"]}
        )
        events_rows = events_result.fetchall()
        events_columns = events_result.keys()

        events = []
        for event_row in events_rows:
            event_dict = dict(zip(events_columns, event_row))
            if event_dict.get("timestamp"):
                event_dict["timestamp"] = event_dict["timestamp"].isoformat()
            events.append(event_dict)

        call_dict["events"] = events
        db.close()

        return call_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/callbacks")
async def get_pending_callbacks(status: str = "pending", limit: int = 50):
    """Get pending callback requests."""
    try:
        db = SessionLocal()

        # Get total count for status
        count_result = db.execute(
            text("SELECT COUNT(*) FROM callback_requests WHERE status = :status"),
            {"status": status}
        )
        total = count_result.scalar() or 0

        # Get callbacks
        result = db.execute(
            text("""
                SELECT
                    cr.id, cr.call_log_id, cr.caller_name, cr.caller_phone,
                    cr.reason, cr.urgency, cr.assigned_to, cr.status,
                    cr.scheduled_at, cr.completed_at, cr.notes, cr.created_at,
                    cl.call_sid, cl.from_number
                FROM callback_requests cr
                LEFT JOIN call_logs cl ON cl.id = cr.call_log_id
                WHERE cr.status = :status
                ORDER BY
                    CASE cr.urgency
                        WHEN 'urgent' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'normal' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END,
                    cr.created_at ASC
                LIMIT :limit
            """),
            {"status": status, "limit": limit}
        )
        rows = result.fetchall()
        columns = result.keys()
        db.close()

        callbacks = []
        for row in rows:
            callback_dict = dict(zip(columns, row))
            # Convert datetime objects to ISO strings
            for key in ["scheduled_at", "completed_at", "created_at"]:
                if callback_dict.get(key):
                    callback_dict[key] = callback_dict[key].isoformat()
            callbacks.append(callback_dict)

        return {"callbacks": callbacks, "total": total, "status": status}

    except Exception as e:
        logger.error(f"Failed to get callbacks: {e}")
        return {"callbacks": [], "total": 0, "error": "Internal server error"}


@app.post("/api/callbacks")
async def create_callback(request: Request):
    """Create a callback request."""
    try:
        data = await request.json()
        db = SessionLocal()

        result = db.execute(
            text("""
                INSERT INTO callback_requests
                    (call_log_id, caller_name, caller_phone, reason, urgency, assigned_to, status, scheduled_at, notes)
                VALUES
                    (:call_log_id, :caller_name, :caller_phone, :reason, :urgency, :assigned_to, 'pending', :scheduled_at, :notes)
                RETURNING id
            """),
            {
                "call_log_id": data.get("call_log_id"),
                "caller_name": data.get("caller_name"),
                "caller_phone": data.get("caller_phone"),
                "reason": data.get("reason"),
                "urgency": data.get("urgency", "normal"),
                "assigned_to": data.get("assigned_to"),
                "scheduled_at": data.get("scheduled_at"),
                "notes": data.get("notes"),
            }
        )
        callback_id = result.scalar()
        db.commit()
        db.close()

        logger.info(f"Callback request created: {callback_id}")
        return {"id": callback_id, "status": "created"}

    except Exception as e:
        logger.error(f"Failed to create callback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.patch("/api/callbacks/{callback_id}")
async def update_callback(callback_id: int, request: Request):
    """Update a callback request status."""
    try:
        data = await request.json()
        db = SessionLocal()

        new_status = data.get("status")
        notes = data.get("notes")

        if new_status == "completed":
            db.execute(
                text("""
                    UPDATE callback_requests
                    SET status = :status, notes = COALESCE(:notes, notes),
                        completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": callback_id, "status": new_status, "notes": notes}
            )
        else:
            db.execute(
                text("""
                    UPDATE callback_requests
                    SET status = :status, notes = COALESCE(:notes, notes),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": callback_id, "status": new_status, "notes": notes}
            )

        db.commit()
        db.close()

        logger.info(f"Callback {callback_id} updated to {new_status}")
        return {"id": callback_id, "status": new_status}

    except Exception as e:
        logger.error(f"Failed to update callback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
