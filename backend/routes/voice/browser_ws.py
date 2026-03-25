"""
Voice Routes - Browser WebSocket for OpenAI Realtime API

Contains:
- /ws/browser-voice WebSocket endpoint
- WebSocket connection rate limiting (H-12 fix)
- Ping/pong heartbeat (C-8 fix)
"""
import logging
import json
import asyncio
import time
import threading
from collections import defaultdict
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from feature_tiers import FeatureTier, get_tier

from .openai_realtime import connect_to_openai_realtime_browser
from .tool_handlers import handle_browser_function_call

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WEBSOCKET CONNECTION RATE LIMITING (H-12 fix)
# ============================================================================

_ws_connections_lock = threading.Lock()
_ws_connections_by_user: Dict[int, int] = defaultdict(int)
_ws_connections_total = 0

MAX_WS_PER_USER = 2
MAX_WS_PER_ORG = 20
MAX_WS_TOTAL = 100


# ============================================================================
# BROWSER WEBSOCKET FOR OPENAI REALTIME API (Talk to Agent)
# ============================================================================

@router.websocket("/ws/browser-voice")
async def browser_voice_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for browser-based voice conversations with AI agents.
    Uses OpenAI Realtime API with PCM16 audio format.

    Client Messages:
    - {"type": "audio", "data": "<base64-pcm16-audio>"}
    - {"type": "text", "text": "..."}

    Server Messages:
    - {"type": "ready"}
    - {"type": "transcript", "text": "...", "role": "user"|"assistant"}
    - {"type": "audio", "data": "<base64-pcm16-audio>"}
    - {"type": "speaking", "is_speaking": true|false}
    - {"type": "error", "message": "..."}
    """
    logger.info(f"Browser voice WebSocket connection from: {websocket.client}")

    # --- CRIT-1: Authenticate BEFORE accepting the WebSocket ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        from auth.tokens import verify_token
        token_data = verify_token(token)
        if not token_data or not token_data.user_id:
            await websocket.close(code=4001, reason="Invalid token claims")
            return
        ws_user_id = token_data.user_id
        ws_organization_id = token_data.tenant_id
        if not ws_organization_id:
            await websocket.close(code=4001, reason="Invalid token claims: missing tenant")
            return
    except Exception as e:
        logger.warning("WebSocket auth failed", extra={"error": str(e)})
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # H-12 fix: Rate limit WebSocket connections per user
    global _ws_connections_total
    with _ws_connections_lock:
        if _ws_connections_total >= MAX_WS_TOTAL:
            logger.warning(f"WebSocket rejected: server at capacity ({_ws_connections_total}/{MAX_WS_TOTAL})")
            await websocket.close(code=4029, reason="Server at capacity")
            return
        user_conn_count = _ws_connections_by_user.get(ws_user_id, 0)
        if user_conn_count >= MAX_WS_PER_USER:
            logger.warning(f"WebSocket rejected: user {ws_user_id} at capacity ({user_conn_count}/{MAX_WS_PER_USER})")
            await websocket.close(code=4029, reason="Too many connections")
            return
        _ws_connections_by_user[ws_user_id] = user_conn_count + 1
        _ws_connections_total += 1

    # --- Feature tier gate: voice_workflows requires PREMIUM ---
    if get_tier("voice_workflows") != FeatureTier.CORE:
        try:
            from db import SessionLocal as _SessionLocal
            _tier_db = _SessionLocal()
            try:
                from database.models import Organization
                org = _tier_db.query(Organization).filter(Organization.id == ws_organization_id).first()
                org_tier = getattr(org, "feature_tier", "core") if org else "core"
                tier_hierarchy = {"core": 0, "premium": 1, "experimental": 2}
                required_level = tier_hierarchy.get(get_tier("voice_workflows").value, 0)
                org_level = tier_hierarchy.get(org_tier, 0)
                if org_level < required_level:
                    await websocket.close(
                        code=4003,
                        reason="This feature requires the 'premium' tier. Contact sales to upgrade.",
                    )
                    return
            finally:
                _tier_db.close()
        except Exception as e:
            logger.warning(f"Feature tier check failed, allowing through: {e}")

    try:
        await websocket.accept()
        logger.info("Browser voice WebSocket accepted", extra={"user_id": ws_user_id})
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        return

    openai_ws = None

    # Derive a session identifier for rate limiting from authenticated user
    ws_session_id = f"user:{ws_user_id}"

    # --- CRIT-3: Use proper session construction instead of get_db().__next__() ---
    from db import SessionLocal
    db = SessionLocal()

    try:
        # Connect to OpenAI Realtime API
        openai_ws = await connect_to_openai_realtime_browser()
        logger.info("Connected to OpenAI Realtime for browser")

        # Send ready signal to client
        await websocket.send_json({"type": "ready"})

        # Handle bidirectional streaming
        async def browser_to_openai():
            """Forward audio from browser to OpenAI"""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    # C-8 fix: Handle ping/pong heartbeat from browser
                    if data.get('type') == 'ping':
                        await websocket.send_json({"type": "pong", "timestamp": time.time()})
                        continue  # Don't forward pings to OpenAI

                    if data.get('type') == 'audio':
                        # Forward audio to OpenAI
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data['data']
                        }))

                    elif data.get('type') == 'text':
                        # Send text message
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": data['text']}]
                            }
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif data.get('type') == 'commit':
                        # Commit audio buffer and request response
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            except WebSocketDisconnect:
                logger.info("Browser disconnected")
            except Exception as e:
                logger.error(f"Error in browser_to_openai: {e}")

        async def openai_to_browser():
            """Forward responses from OpenAI to browser"""
            try:
                async for message in openai_ws:
                    data = json.loads(message)
                    event_type = data.get('type', '')

                    if event_type == 'response.audio.delta':
                        # Forward audio chunk to browser
                        audio_data = data.get('delta', '')
                        if audio_data:
                            await websocket.send_json({
                                "type": "audio",
                                "data": audio_data
                            })

                    elif event_type == 'response.audio_transcript.delta':
                        # AI is speaking - send transcript
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('delta', ''),
                            "role": "assistant",
                            "is_final": False
                        })

                    elif event_type == 'response.audio_transcript.done':
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('transcript', ''),
                            "role": "assistant",
                            "is_final": True
                        })

                    elif event_type == 'conversation.item.input_audio_transcription.completed':
                        # User speech transcription complete
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get('transcript', ''),
                            "role": "user",
                            "is_final": True
                        })

                    elif event_type == 'input_audio_buffer.speech_started':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "user",
                            "is_speaking": True
                        })

                    elif event_type == 'input_audio_buffer.speech_stopped':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "user",
                            "is_speaking": False
                        })

                    elif event_type == 'response.audio.done':
                        await websocket.send_json({
                            "type": "speaking",
                            "who": "assistant",
                            "is_speaking": False
                        })

                    elif event_type == 'response.function_call_arguments.done':
                        # Handle CRM tool calls from the AI
                        func_name = data.get('name', '')
                        func_args_str = data.get('arguments', '{}')
                        call_id = data.get('call_id', '')

                        logger.info(f"Browser voice function call: {func_name} with args: {func_args_str}")

                        try:
                            args = json.loads(func_args_str)

                            # --- HIGH-1: Validate function call arguments ---
                            if not isinstance(args, dict):
                                raise ValueError("Function arguments must be a JSON object")
                            for key, val in args.items():
                                if isinstance(val, str) and len(val) > 2000:
                                    raise ValueError(f"Argument '{key}' exceeds max length (2000 chars)")
                                if not isinstance(key, str) or len(key) > 100:
                                    raise ValueError(f"Invalid argument key: {str(key)[:50]}")

                            # Notify browser that an action is in progress
                            await websocket.send_json({
                                "type": "action",
                                "action": func_name,
                                "params": args,
                                "status": "pending"
                            })

                            # Execute the function (CRIT-2: pass organization_id for tenant scoping)
                            result = await handle_browser_function_call(
                                func_name, args, db, session_id=ws_session_id,
                                organization_id=ws_organization_id, user_id=ws_user_id
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

                            # Notify browser of completion
                            action_status = "success" if result.get("success", False) else "error"
                            await websocket.send_json({
                                "type": "action",
                                "action": func_name,
                                "params": args,
                                "result": result,
                                "status": action_status
                            })

                            logger.info(f"Browser function {func_name} completed: {action_status}")

                        except Exception as func_err:
                            logger.error(f"Browser function call error: {func_err}")
                            # Still send result back to OpenAI so it can inform the user
                            error_result = {"success": False, "message": f"Error executing {func_name}: {str(func_err)}"}
                            try:
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(error_result)
                                    }
                                }))
                                await openai_ws.send(json.dumps({
                                    "type": "response.create"
                                }))
                            except Exception as send_err:
                                logger.error(f"Failed to send error result to OpenAI: {send_err}")
                            await websocket.send_json({
                                "type": "action",
                                "action": func_name,
                                "params": {},
                                "result": error_result,
                                "status": "error"
                            })

                    elif event_type == 'error':
                        error_msg = data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"OpenAI error: {error_msg}")
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })

            except Exception as e:
                logger.error(f"Error in openai_to_browser: {e}")

        # Run both directions concurrently
        await asyncio.gather(
            browser_to_openai(),
            openai_to_browser()
        )

    except Exception as e:
        logger.error(f"Browser voice error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception as e:
            logger.error(f"Error in browser_voice_session (send error to client): {e}")
            pass  # Client may have disconnected
    finally:
        if openai_ws:
            try:
                await openai_ws.close()
            except Exception as e:
                logger.error(f"Error in browser_voice_session (close openai_ws): {e}")
                pass  # WebSocket may already be closed
        # Close database session
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error closing db session in browser voice: {e}")
        # H-12 fix: Decrement connection counters
        with _ws_connections_lock:
            if ws_user_id in _ws_connections_by_user:
                _ws_connections_by_user[ws_user_id] = max(0, _ws_connections_by_user[ws_user_id] - 1)
                if _ws_connections_by_user[ws_user_id] == 0:
                    del _ws_connections_by_user[ws_user_id]
            _ws_connections_total = max(0, _ws_connections_total - 1)
        logger.info("Browser voice session ended")
