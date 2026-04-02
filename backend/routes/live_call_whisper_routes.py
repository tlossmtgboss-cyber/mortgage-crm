"""
Live Call Whisper Routes

WebSocket and REST API endpoints for real-time call whispers.
Part of the Conversation Intelligence module.
"""

import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from utils.websocket_auth import authenticate_websocket
from services.live_call_whisper_service import (
    LiveCallWhisperService,
    CallContext,
    Whisper,
    WhisperType,
)

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/call-whisper", tags=["Live Call Whisper"],
    dependencies=[Depends(_get_current_user())],
)

# Global service instance and connection manager
whisper_service = LiveCallWhisperService()


class ConnectionManager:
    """Manage WebSocket connections for live calls."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, call_id: str, skip_accept: bool = False):
        if not skip_accept:
            await websocket.accept()
        if call_id not in self.active_connections:
            self.active_connections[call_id] = []
        self.active_connections[call_id].append(websocket)
        logger.info(f"WebSocket connected for call {call_id}")

    def disconnect(self, websocket: WebSocket, call_id: str):
        if call_id in self.active_connections:
            if websocket in self.active_connections[call_id]:
                self.active_connections[call_id].remove(websocket)
            if not self.active_connections[call_id]:
                del self.active_connections[call_id]
        logger.info(f"WebSocket disconnected for call {call_id}")

    async def broadcast_whisper(self, call_id: str, whisper: Whisper):
        """Broadcast a whisper to all connected clients for a call."""
        if call_id in self.active_connections:
            message = {
                "type": "whisper",
                "data": whisper.to_dict(),
            }
            for connection in self.active_connections[call_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send whisper: {e}")

    async def broadcast_whispers(self, call_id: str, whispers: List[Whisper]):
        """Broadcast multiple whispers."""
        for whisper in whispers:
            await self.broadcast_whisper(call_id, whisper)


manager = ConnectionManager()


# =============================================================================
# Request/Response Models
# =============================================================================

class StartCallRequest(BaseModel):
    """Request to start a call session."""
    call_id: str = Field(..., description="Unique call identifier")
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    caller_name: Optional[str] = None
    caller_type: str = "prospect"
    loan_purpose: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    credit_score: Optional[int] = None


class TranscriptRequest(BaseModel):
    """Request to process a transcript segment."""
    speaker: str = Field(..., description="'agent' or 'caller'")
    text: str = Field(..., description="Transcript text")
    confidence: float = Field(default=1.0, ge=0, le=1)


class WhisperRequest(BaseModel):
    """Request for AI-generated whisper."""
    prompt: str = Field(..., description="What kind of suggestion do you need?")


class WhisperResponse(BaseModel):
    """Whisper response model."""
    id: str
    type: str
    priority: str
    title: str
    content: str
    context: str
    timestamp: str
    dismissed: bool
    used: bool


class CallContextResponse(BaseModel):
    """Call context response model."""
    call_id: str
    caller_name: str
    caller_type: str
    loan_purpose: Optional[str]
    call_stage: str
    sentiment: str
    duration_seconds: int
    topics_discussed: List[str]
    objections_raised: List[str]


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/{call_id}")
async def websocket_endpoint(websocket: WebSocket, call_id: str):
    """
    WebSocket endpoint for real-time whisper communication.
    Requires JWT authentication.

    Connect to receive real-time whispers during a call.
    Send transcript segments to trigger whisper generation.

    Message types:
    - Outgoing: {"type": "whisper", "data": {...}}
    - Outgoing: {"type": "connected", "call_id": "..."}
    - Incoming: {"type": "transcript", "speaker": "agent|caller", "text": "..."}
    - Incoming: {"type": "dismiss", "whisper_id": "..."}
    - Incoming: {"type": "used", "whisper_id": "..."}
    - Incoming: {"type": "ask", "prompt": "..."}
    """
    await websocket.accept()

    # Authenticate
    auth_db = next(get_db())
    try:
        user, auth_error = authenticate_websocket(websocket, auth_db)
        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        auth_db.close()

    await manager.connect(websocket, call_id, skip_accept=True)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "call_id": call_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Send any existing whispers
        existing_whispers = whisper_service.get_active_whispers(call_id)
        for whisper in existing_whispers:
            await websocket.send_json({
                "type": "whisper",
                "data": whisper.to_dict(),
            })

        while True:
            # Receive message from client
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "transcript":
                # Process transcript and get new whispers
                whispers = await whisper_service.process_transcript(
                    call_id=call_id,
                    speaker=data.get("speaker", "caller"),
                    text=data.get("text", ""),
                    confidence=data.get("confidence", 1.0),
                )
                # Broadcast new whispers
                await manager.broadcast_whispers(call_id, whispers)

            elif msg_type == "dismiss":
                # Dismiss a whisper
                whisper_id = data.get("whisper_id")
                if whisper_id:
                    whisper_service.dismiss_whisper(call_id, whisper_id)
                    await websocket.send_json({
                        "type": "dismissed",
                        "whisper_id": whisper_id,
                    })

            elif msg_type == "used":
                # Mark whisper as used
                whisper_id = data.get("whisper_id")
                if whisper_id:
                    whisper_service.mark_whisper_used(call_id, whisper_id)
                    await websocket.send_json({
                        "type": "marked_used",
                        "whisper_id": whisper_id,
                    })

            elif msg_type == "ask":
                # Request AI-generated whisper
                prompt = data.get("prompt", "")
                if prompt:
                    whisper = await whisper_service.get_ai_whisper(call_id, prompt)
                    if whisper:
                        await manager.broadcast_whisper(call_id, whisper)

            elif msg_type == "ping":
                # Keep-alive ping
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, call_id)
    except Exception as e:
        logger.error(f"WebSocket error for call {call_id}: {e}")
        manager.disconnect(websocket, call_id)


# =============================================================================
# REST API Endpoints
# =============================================================================

@router.post("/start", response_model=CallContextResponse)
async def start_call(request: StartCallRequest):
    """
    Start a new call session and get initial whispers.

    Call this when a call begins to initialize the whisper session.
    """
    caller_info = {
        "name": request.caller_name,
        "type": request.caller_type,
        "loan_purpose": request.loan_purpose,
        "loan_type": request.loan_type,
        "loan_amount": request.loan_amount,
        "credit_score": request.credit_score,
    }

    context = await whisper_service.start_call(
        call_id=request.call_id,
        lead_id=request.lead_id,
        loan_id=request.loan_id,
        caller_info=caller_info,
    )

    return CallContextResponse(
        call_id=context.call_id,
        caller_name=context.caller_name,
        caller_type=context.caller_type,
        loan_purpose=context.loan_purpose,
        call_stage=context.call_stage,
        sentiment=context.sentiment,
        duration_seconds=context.duration_seconds,
        topics_discussed=context.topics_discussed,
        objections_raised=context.objections_raised,
    )


@router.post("/{call_id}/transcript", response_model=List[WhisperResponse])
async def process_transcript(
    call_id: str,
    request: TranscriptRequest,
):
    """
    Process a transcript segment and get new whispers.

    Use this endpoint if not using WebSockets.
    """
    whispers = await whisper_service.process_transcript(
        call_id=call_id,
        speaker=request.speaker,
        text=request.text,
        confidence=request.confidence,
    )

    # Also broadcast via WebSocket if connected
    await manager.broadcast_whispers(call_id, whispers)

    return [
        WhisperResponse(
            id=w.id,
            type=w.type.value,
            priority=w.priority.value,
            title=w.title,
            content=w.content,
            context=w.context,
            timestamp=w.timestamp.isoformat(),
            dismissed=w.dismissed,
            used=w.used,
        )
        for w in whispers
    ]


@router.get("/{call_id}/whispers", response_model=List[WhisperResponse])
async def get_whispers(
    call_id: str,
    include_dismissed: bool = Query(default=False),
):
    """
    Get all whispers for a call.
    """
    all_whispers = whisper_service.call_whispers.get(call_id, [])

    if not include_dismissed:
        all_whispers = [w for w in all_whispers if not w.dismissed]

    return [
        WhisperResponse(
            id=w.id,
            type=w.type.value,
            priority=w.priority.value,
            title=w.title,
            content=w.content,
            context=w.context,
            timestamp=w.timestamp.isoformat(),
            dismissed=w.dismissed,
            used=w.used,
        )
        for w in all_whispers
    ]


@router.post("/{call_id}/ask", response_model=Optional[WhisperResponse])
async def ask_for_whisper(
    call_id: str,
    request: WhisperRequest,
):
    """
    Ask for an AI-generated whisper on demand.
    """
    whisper = await whisper_service.get_ai_whisper(call_id, request.prompt)

    if not whisper:
        raise HTTPException(status_code=500, detail="Failed to generate whisper")

    # Broadcast via WebSocket
    await manager.broadcast_whisper(call_id, whisper)

    return WhisperResponse(
        id=whisper.id,
        type=whisper.type.value,
        priority=whisper.priority.value,
        title=whisper.title,
        content=whisper.content,
        context=whisper.context,
        timestamp=whisper.timestamp.isoformat(),
        dismissed=whisper.dismissed,
        used=whisper.used,
    )


@router.post("/{call_id}/dismiss/{whisper_id}")
async def dismiss_whisper(call_id: str, whisper_id: str):
    """
    Dismiss a whisper.
    """
    success = whisper_service.dismiss_whisper(call_id, whisper_id)
    if not success:
        raise HTTPException(status_code=404, detail="Whisper not found")
    return {"status": "dismissed", "whisper_id": whisper_id}


@router.post("/{call_id}/used/{whisper_id}")
async def mark_whisper_used(call_id: str, whisper_id: str):
    """
    Mark a whisper as used by the agent.
    """
    success = whisper_service.mark_whisper_used(call_id, whisper_id)
    if not success:
        raise HTTPException(status_code=404, detail="Whisper not found")
    return {"status": "marked_used", "whisper_id": whisper_id}


@router.post("/{call_id}/end")
async def end_call(call_id: str):
    """
    End a call session and get summary.
    """
    summary = await whisper_service.end_call(call_id)

    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])

    return summary


@router.get("/{call_id}/context", response_model=CallContextResponse)
async def get_call_context(call_id: str):
    """
    Get current call context.
    """
    if call_id not in whisper_service.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")

    context = whisper_service.active_calls[call_id]

    return CallContextResponse(
        call_id=context.call_id,
        caller_name=context.caller_name,
        caller_type=context.caller_type,
        loan_purpose=context.loan_purpose,
        call_stage=context.call_stage,
        sentiment=context.sentiment,
        duration_seconds=context.duration_seconds,
        topics_discussed=context.topics_discussed,
        objections_raised=context.objections_raised,
    )


@router.get("/{call_id}/compliance")
async def get_compliance_reminders(call_id: str):
    """
    Get compliance reminders for the current call.
    """
    if call_id not in whisper_service.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")

    context = whisper_service.active_calls[call_id]
    reminders = await whisper_service.get_compliance_reminders(context)

    return [
        WhisperResponse(
            id=w.id,
            type=w.type.value,
            priority=w.priority.value,
            title=w.title,
            content=w.content,
            context=w.context,
            timestamp=w.timestamp.isoformat(),
            dismissed=w.dismissed,
            used=w.used,
        )
        for w in reminders
    ]


@router.get("/active-calls")
async def get_active_calls():
    """
    Get list of active call sessions.
    """
    return {
        "active_calls": [
            {
                "call_id": call_id,
                "caller_name": ctx.caller_name,
                "duration_seconds": ctx.duration_seconds,
                "call_stage": ctx.call_stage,
            }
            for call_id, ctx in whisper_service.active_calls.items()
        ],
        "total": len(whisper_service.active_calls),
    }


@router.get("/health")
async def whisper_health():
    """Health check for the whisper service."""
    return {
        "status": "healthy",
        "service": "live-call-whisper",
        "active_calls": len(whisper_service.active_calls),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
