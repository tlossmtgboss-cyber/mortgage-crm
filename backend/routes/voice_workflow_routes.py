"""
Voice Workflow Routes - WebSocket and REST endpoints

Provides real-time voice-driven workflow interaction via WebSocket,
plus REST endpoints for session management and status.
"""
import os
import json
import logging
import asyncio
import base64
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import aiohttp

from models.voice_workflow_models import (
    WorkflowType,
    WorkflowSessionCreate,
    ServerMessage,
    WebSocketMessageType,
)
from services.voice_workflow_service import get_workflow_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice-workflow", tags=["Voice Workflow"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None


from db import get_db


def set_dependencies(get_db_func):
    """Set dependencies from main.py."""
    global _get_db
    _get_db = get_db_func
    logger.info("Voice Workflow routes dependencies set")


async def get_current_user_id(
    request: Request,
    db: Session = Depends(get_db),
) -> int:
    """Get user ID from Authorization header (supports JWT and session tokens).

    Extracts the token from the 'Authorization: Bearer <token>' header.
    Note: The WebSocket endpoint (/ws) passes the token via query parameter
    directly because WebSocket connections cannot reliably use HTTP headers.
    """
    from auth.tokens import verify_access_token

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]  # Strip "Bearer " prefix

    # Verify token with blacklist check
    payload = verify_access_token(token)
    if payload:
        email = payload.get("sub")
        if email:
            result = db.execute(text("""
                SELECT id FROM users WHERE email = :email
            """), {"email": email}).fetchone()
            if result:
                return result[0]

    # Fall back to session token
    result = db.execute(text("""
        SELECT user_id FROM sessions
        WHERE token = :token AND expires_at > NOW()
    """), {"token": token}).fetchone()

    if result:
        return result[0]

    raise HTTPException(status_code=401, detail="Invalid or expired token")


# =============================================================================
# DEEPGRAM STT
# =============================================================================

async def transcribe_audio(audio_data: bytes) -> Optional[str]:
    """Transcribe audio using Deepgram API."""
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    if not deepgram_key:
        logger.warning("Deepgram API key not configured")
        return None

    try:
        url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"

        headers = {
            "Authorization": f"Token {deepgram_key}",
            "Content-Type": "audio/webm",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=audio_data, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    transcript = result.get("results", {}).get("channels", [{}])[0].get(
                        "alternatives", [{}]
                    )[0].get("transcript", "")
                    return transcript if transcript else None
                else:
                    error = await response.text()
                    logger.error(f"Deepgram error: {response.status} - {error}")
                    return None

    except SQLAlchemyError as e:
        logger.error(f"Transcription error: {e}")
        return None


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@router.websocket("/ws")
async def voice_workflow_websocket(
    websocket: WebSocket,
    token: str = Query(None),
):
    """
    WebSocket endpoint for real-time voice workflow interaction.

    Security: Token sent as first message after connect (not in URL query string)
    to avoid leaking JWT into server/proxy access logs and browser history.
    Backwards compatible: old clients with ?token= query param still work.

    Protocol:
    - Client sends: {"type": "auth", "token": "..."} (first message if no ?token= in URL)
    - Client sends: {"type": "audio", "data": "<base64>"}
    - Client sends: {"type": "text_input", "text": "John Smith"}
    - Client sends: {"type": "start_workflow", "workflow_type": "pre_approval_letter"}
    - Client sends: {"type": "cancel_workflow"}

    - Server sends: {"type": "workflow_started", "workflow_id": "...", "current_state": "..."}
    - Server sends: {"type": "state_changed", "current_state": "...", "slots_collected": {...}}
    - Server sends: {"type": "response_audio", "audio_data": "<base64>", "text": "..."}
    - Server sends: {"type": "workflow_completed", "result": {...}}
    - Server sends: {"type": "error", "error": "..."}
    """
    await websocket.accept()

    # Get database session - need to handle generator properly
    db = None
    db_gen = None

    try:
        db_gen = get_db()
        db = next(db_gen)
    except Exception as db_err:
        logger.error(f"Failed to get database session: {db_err}")
        await websocket.send_json({
            "type": WebSocketMessageType.ERROR.value,
            "error": "Database connection failed"
        })
        await websocket.close()
        return

    try:
        user_id = None

        # If no token in URL, wait for first-message auth
        if not token:
            import asyncio as _asyncio
            import json as _json
            try:
                raw = await _asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                msg = _json.loads(raw)
                if isinstance(msg, dict) and msg.get("type") == "auth":
                    token = msg.get("token", "")
            except (_asyncio.TimeoutError, Exception):
                pass

        if not token:
            await websocket.send_json({
                "type": WebSocketMessageType.ERROR.value,
                "error": "Authentication required"
            })
            await websocket.close()
            return

        # First try JWT token via centralized auth (handles RS256/HS256 + blacklist)
        try:
            from auth.tokens import verify_access_token
            payload = verify_access_token(token)
            if payload:
                email = payload.get("sub")
                if email:
                    result = db.execute(text("""
                        SELECT id FROM users WHERE email = :email
                    """), {"email": email}).fetchone()
                    if result:
                        user_id = result[0]
                if not user_id:
                    user_id = payload.get("user_id")
        except Exception as _exc:  # noqa: BLE001
            pass  # Not a valid JWT, try session token

        # Fall back to session token
        if not user_id:
            result = db.execute(text("""
                SELECT user_id FROM sessions
                WHERE token = :token AND expires_at > NOW()
            """), {"token": token}).fetchone()
            if result:
                user_id = result[0]

        if not user_id:
            await websocket.send_json({
                "type": WebSocketMessageType.ERROR.value,
                "error": "Invalid or expired token"
            })
            await websocket.close()
            return

        workflow_service = get_workflow_service(db)

        # Check for existing active session
        session = await workflow_service.get_active_session(user_id)

        logger.info(f"Voice workflow WebSocket connected for user {user_id}")

        while True:
            try:
                # Receive message
                message = await websocket.receive_json()
                msg_type = message.get("type")

                # Start new workflow
                if msg_type == "start_workflow":
                    workflow_type_str = message.get("workflow_type", "pre_approval_letter")
                    try:
                        workflow_type = WorkflowType(workflow_type_str)
                    except ValueError:
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": f"Unknown workflow type: {workflow_type_str}"
                        })
                        continue

                    # Create new session
                    try:
                        logger.info(f"Creating workflow session for user {user_id}, type: {workflow_type}")
                        session, response = await workflow_service.create_session(
                            user_id=user_id,
                            workflow_type=workflow_type,
                            initial_transcript=message.get("transcript"),
                        )
                        logger.info(f"Session created: {session.id}, state: {session.current_state}")
                    except Exception as create_err:
                        import traceback
                        logger.error(f"Failed to create session: {create_err}")
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": f"Failed to create session: {str(create_err)}"
                        })
                        continue

                    # Send workflow started
                    await websocket.send_json({
                        "type": WebSocketMessageType.WORKFLOW_STARTED.value,
                        "workflow_id": str(session.id),
                        "current_state": session.current_state,
                    })

                    # Send response
                    await websocket.send_json({
                        "type": WebSocketMessageType.RESPONSE_AUDIO.value,
                        "text": response.get("text"),
                        "audio_data": response.get("audio_base64"),
                        "current_state": session.current_state,
                        "options": response.get("options"),
                    })

                # Handle audio input
                elif msg_type == "audio":
                    if not session:
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": "No active workflow. Send 'start_workflow' first."
                        })
                        continue

                    # Decode and transcribe audio
                    audio_base64 = message.get("data", "")
                    try:
                        audio_bytes = base64.b64decode(audio_base64)
                    except Exception as e:
                        logger.warning(f"Invalid base64 audio in voice_workflow_websocket: {e}")
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": "Invalid base64 audio data"
                        })
                        continue

                    transcript = await transcribe_audio(audio_bytes)

                    if not transcript:
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": "Could not transcribe audio"
                        })
                        continue

                    # Process the transcript
                    response = await workflow_service.process_user_input(
                        session=session,
                        transcript=transcript,
                        audio_duration_ms=message.get("duration_ms"),
                    )

                    # Check if workflow completed
                    if not session.is_active:
                        await websocket.send_json({
                            "type": WebSocketMessageType.WORKFLOW_COMPLETED.value,
                            "result": response.get("result_data", {}),
                            "text": response.get("text"),
                            "audio_data": response.get("audio_base64"),
                        })
                        session = None
                    else:
                        # Send state change and response
                        await websocket.send_json({
                            "type": WebSocketMessageType.STATE_CHANGED.value,
                            "current_state": session.current_state,
                            "slots_collected": session.slots,
                        })

                        await websocket.send_json({
                            "type": WebSocketMessageType.RESPONSE_AUDIO.value,
                            "text": response.get("text"),
                            "audio_data": response.get("audio_base64"),
                            "options": response.get("options"),
                        })

                # Handle text input (for testing/accessibility)
                elif msg_type == "text_input":
                    if not session:
                        await websocket.send_json({
                            "type": WebSocketMessageType.ERROR.value,
                            "error": "No active workflow. Send 'start_workflow' first."
                        })
                        continue

                    transcript = message.get("text", "")

                    # Process the transcript
                    response = await workflow_service.process_user_input(
                        session=session,
                        transcript=transcript,
                    )

                    # Check if workflow completed
                    if not session.is_active:
                        await websocket.send_json({
                            "type": WebSocketMessageType.WORKFLOW_COMPLETED.value,
                            "result": response.get("result_data", {}),
                            "text": response.get("text"),
                            "audio_data": response.get("audio_base64"),
                        })
                        session = None
                    else:
                        await websocket.send_json({
                            "type": WebSocketMessageType.STATE_CHANGED.value,
                            "current_state": session.current_state,
                            "slots_collected": session.slots,
                        })

                        await websocket.send_json({
                            "type": WebSocketMessageType.RESPONSE_AUDIO.value,
                            "text": response.get("text"),
                            "audio_data": response.get("audio_base64"),
                            "options": response.get("options"),
                        })

                # Cancel workflow
                elif msg_type == "cancel_workflow":
                    if session:
                        await workflow_service.cancel_session(session.id)
                        await websocket.send_json({
                            "type": WebSocketMessageType.WORKFLOW_CANCELLED.value,
                        })
                        session = None

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {user_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": WebSocketMessageType.ERROR.value,
                    "error": "Invalid JSON message"
                })
            except SQLAlchemyError as e:
                import traceback
                logger.error(f"WebSocket message error: {e}")
                try:
                    await websocket.send_json({
                        "type": WebSocketMessageType.ERROR.value,
                        "error": "Internal server error"
                    })
                except Exception as e:
                    logger.warning(f"Failed to send error to websocket in voice_workflow_websocket: {e}")

    except Exception as e:
        import traceback
        logger.error(f"WebSocket connection error: {e}")
    finally:
        if db_gen:
            try:
                next(db_gen)
            except StopIteration:
                pass


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@router.post("/sessions")
async def create_workflow_session(
    request: WorkflowSessionCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create a new voice workflow session."""
    try:
        workflow_service = get_workflow_service(db)

        session, response = await workflow_service.create_session(
            user_id=user_id,
            workflow_type=request.workflow_type,
            initial_transcript=request.initial_transcript,
        )

        return {
            "success": True,
            "workflow_id": str(session.id),
            "current_state": session.current_state,
            "response": response,
        }
    except SQLAlchemyError as e:
        logger.error(f"Error creating workflow session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/sessions/{user_id}")
async def get_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Get workflow sessions for a user."""
    results = db.execute(text("""
        SELECT id, workflow_type, current_state, started_at, completed_at, is_active
        FROM voice_workflow_sessions
        WHERE user_id = :user_id
        ORDER BY started_at DESC
        LIMIT 20
    """), {"user_id": user_id}).fetchall()

    return {
        "sessions": [
            {
                "id": str(r[0]),
                "workflow_type": r[1],
                "current_state": r[2],
                "started_at": r[3].isoformat() if r[3] else None,
                "completed_at": r[4].isoformat() if r[4] else None,
                "is_active": r[5],
            }
            for r in results
        ]
    }


@router.get("/session/{workflow_id}")
async def get_session_details(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    """Get details of a specific workflow session."""
    try:
        workflow_service = get_workflow_service(db)

        try:
            session = await workflow_service.get_session(UUID(workflow_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workflow ID")

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return {
            "id": str(session.id),
            "user_id": session.user_id,
            "workflow_type": session.workflow_type.value,
            "current_state": session.current_state,
            "slots": session.slots,
            "conversation_history": [
                {
                    "role": t.role,
                    "content": t.content,
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                }
                for t in session.conversation_history
            ],
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "is_active": session.is_active,
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error getting session details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get session")


@router.post("/session/{workflow_id}/input")
async def process_workflow_input(
    workflow_id: str,
    request: dict,
    db: Session = Depends(get_db),
):
    """Process text input for a workflow session (for testing)."""
    workflow_service = get_workflow_service(db)

    try:
        session = await workflow_service.get_session(UUID(workflow_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow ID")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is no longer active")

    transcript = request.get("text", "")
    if not transcript:
        raise HTTPException(status_code=400, detail="No text provided")

    response = await workflow_service.process_user_input(
        session=session,
        transcript=transcript,
    )

    return {
        "success": True,
        "current_state": session.current_state,
        "slots": session.slots,
        "is_active": session.is_active,
        "response": response,
    }


@router.delete("/session/{workflow_id}")
async def cancel_workflow_session(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    """Cancel a workflow session."""
    workflow_service = get_workflow_service(db)

    try:
        await workflow_service.cancel_session(UUID(workflow_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow ID")

    return {"success": True, "message": "Session cancelled"}


@router.get("/workflow-types")
async def list_workflow_types():
    """List available workflow types."""
    return {
        "workflow_types": [
            {
                "type": wt.value,
                "name": wt.name.replace("_", " ").title(),
                "description": _get_workflow_description(wt),
            }
            for wt in WorkflowType
        ]
    }


def _get_workflow_description(wt: WorkflowType) -> str:
    """Get human-readable description for workflow type."""
    descriptions = {
        WorkflowType.PRE_APPROVAL_LETTER: "Generate and send pre-approval letters to realtors",
        WorkflowType.SCHEDULE_APPOINTMENT: "Schedule meetings with contacts",
        WorkflowType.CREATE_TASK: "Create tasks and reminders",
        WorkflowType.SEND_EMAIL: "Send emails to borrowers or realtors",
        WorkflowType.UPDATE_LOAN_STATUS: "Update loan pipeline status",
    }
    return descriptions.get(wt, "")
