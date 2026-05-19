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
# NOTE: This counter is process-local. In multi-worker deployments (Railway with >1 worker),
# each worker tracks independently. For true rate limiting, use Redis-backed counter.
# TODO: Migrate to Redis-based connection tracking for multi-worker support.
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

    # --- Security: Support post-connect auth to avoid token in URL ---
    # Backwards compatible: old clients with ?token= query param still work.
    token = websocket.query_params.get("token")

    if token:
        # Legacy path: token in query string (still works for old clients)
        try:
            from auth.tokens import verify_token
            token_data = verify_token(token)
            if not token_data or not token_data.user_id:
                try:
                    await websocket.close(code=4001, reason="Invalid token claims")
                except RuntimeError:
                    pass
                return
            ws_user_id = token_data.user_id
            ws_organization_id = token_data.tenant_id
            if not ws_organization_id:
                try:
                    await websocket.close(code=4001, reason="Invalid token claims: missing tenant")
                except RuntimeError:
                    pass
                return
        except Exception as e:
            logger.warning("WebSocket auth failed", extra={"error": str(e)})
            try:
                await websocket.close(code=4001, reason="Authentication failed")
            except RuntimeError:
                pass
            return
    else:
        # Secure path: accept first, then read token from first message
        import asyncio
        import json as _json
        try:
            await websocket.accept()
        except Exception as e:
            logger.error(f"Failed to accept WebSocket: {e}")
            return

        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            msg = _json.loads(raw)
            if not isinstance(msg, dict) or msg.get("type") != "auth" or not msg.get("token"):
                await websocket.send_json({"type": "error", "message": "First message must be auth"})
                await websocket.close(code=4001, reason="Authentication required")
                return
            token = msg["token"]
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "error", "message": "Authentication timeout"})
            await websocket.close(code=4001, reason="Authentication timeout")
            return
        except Exception as e:
            logger.warning("WebSocket auth message error", extra={"error": str(e)})
            try:
                await websocket.close(code=4001, reason="Authentication failed")
            except RuntimeError:
                pass
            return

        try:
            from auth.tokens import verify_token
            token_data = verify_token(token)
            if not token_data or not token_data.user_id:
                await websocket.send_json({"type": "error", "message": "Invalid token"})
                await websocket.close(code=4001, reason="Invalid token claims")
                return
            ws_user_id = token_data.user_id
            ws_organization_id = token_data.tenant_id
            if not ws_organization_id:
                await websocket.send_json({"type": "error", "message": "Invalid token: missing tenant"})
                await websocket.close(code=4001, reason="Invalid token claims: missing tenant")
                return
        except Exception as e:
            logger.warning("WebSocket auth failed", extra={"error": str(e)})
            await websocket.send_json({"type": "error", "message": "Authentication failed"})
            await websocket.close(code=4001, reason="Authentication failed")
            return

    # H-12 fix: Rate limit WebSocket connections per user
    global _ws_connections_total
    with _ws_connections_lock:
        if _ws_connections_total >= MAX_WS_TOTAL:
            logger.warning(f"WebSocket rejected: server at capacity ({_ws_connections_total}/{MAX_WS_TOTAL})")
            try:
                await websocket.close(code=4029, reason="Server at capacity")
            except RuntimeError:
                pass  # WebSocket already closed
            return
        user_conn_count = _ws_connections_by_user.get(ws_user_id, 0)
        if user_conn_count >= MAX_WS_PER_USER:
            logger.warning(f"WebSocket rejected: user {ws_user_id} at capacity ({user_conn_count}/{MAX_WS_PER_USER})")
            try:
                await websocket.close(code=4029, reason="Too many connections")
            except RuntimeError:
                pass  # WebSocket already closed
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
                    try:
                        await websocket.close(
                            code=4003,
                            reason="This feature requires the 'premium' tier. Contact sales to upgrade.",
                        )
                    except RuntimeError:
                        pass  # WebSocket already closed
                    finally:
                        # MED-6: Ensure rate limiter is always decremented on early return
                        with _ws_connections_lock:
                            if ws_user_id in _ws_connections_by_user:
                                _ws_connections_by_user[ws_user_id] = max(0, _ws_connections_by_user[ws_user_id] - 1)
                                if _ws_connections_by_user[ws_user_id] == 0:
                                    del _ws_connections_by_user[ws_user_id]
                            _ws_connections_total = max(0, _ws_connections_total - 1)
                    return
            finally:
                _tier_db.close()
        except Exception as e:
            logger.warning(f"Feature tier check failed, allowing through: {e}")

    # Accept WebSocket if not already accepted (secure path accepts early for auth message)
    _already_accepted = not websocket.query_params.get("token")
    if not _already_accepted:
        try:
            await websocket.accept()
            logger.info("Browser voice WebSocket accepted", extra={"user_id": ws_user_id})
        except Exception as e:
            logger.error(f"Failed to accept WebSocket: {e}")
            # MED-6: Ensure rate limiter is always decremented on early return
            with _ws_connections_lock:
                if ws_user_id in _ws_connections_by_user:
                    _ws_connections_by_user[ws_user_id] = max(0, _ws_connections_by_user[ws_user_id] - 1)
                    if _ws_connections_by_user[ws_user_id] == 0:
                        del _ws_connections_by_user[ws_user_id]
                _ws_connections_total = max(0, _ws_connections_total - 1)
            return
    else:
        logger.info("Browser voice WebSocket already accepted (post-connect auth)", extra={"user_id": ws_user_id})

    openai_ws = None

    # Derive a session identifier for rate limiting from authenticated user
    ws_session_id = f"user:{ws_user_id}"

    # --- CRIT-3: Use proper session construction instead of get_db().__next__() ---
    from db import SessionLocal
    db = SessionLocal()

    # --- CI transcript accumulation state ---
    # Tracks the active Call Intelligence session and accumulates transcript
    # text from OpenAI Realtime speech-to-text events so it can be persisted
    # to call_sessions.full_transcript when recording stops.
    ci_lock = asyncio.Lock()  # HIGH-3: Protect concurrent access to ci_state transcript_parts
    ci_state = {
        "session_id": None,       # Set when start_call_recording succeeds
        "transcript_parts": [],   # List of (role, text) tuples
        "flushed_index": 0,       # P2: Index of last flushed part
        "flush_task": None,       # P2: Reference to periodic flush task
        "needs_flush": False,     # HIGH-4: Flag for early flush when buffer exceeds cap
    }

    # P2: Periodic transcript flush coroutine
    async def _flush_transcript_periodically():
        """Flush accumulated transcript to DB every 30 seconds."""
        FLUSH_INTERVAL = 30
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            async with ci_lock:
                sid = ci_state.get("session_id")
                parts = ci_state.get("transcript_parts", [])
                flushed = ci_state.get("flushed_index", 0)
                needs_flush = ci_state.get("needs_flush", False)
                if not sid or (flushed >= len(parts) and not needs_flush):
                    continue
                new_parts = parts[flushed:]
                ci_state["needs_flush"] = False
            chunk = "\n".join(f"[{role}]: {txt}" for role, txt in new_parts)
            try:
                from services.voice_ci_bridge_service import VoiceCIBridgeService
                bridge = VoiceCIBridgeService(db, ws_organization_id, ws_user_id)
                await bridge.append_transcript_chunk(sid, chunk)
                db.commit()
                async with ci_lock:
                    ci_state["flushed_index"] = len(parts)
                logger.debug(f"CI transcript flushed: {len(new_parts)} parts for session {sid[:8]}")
            except Exception as flush_err:
                logger.warning(f"Periodic transcript flush failed: {flush_err}")
                try:
                    db.rollback()
                except Exception as _exc:  # noqa: BLE001
                    pass

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
                        transcript_text = data.get('transcript', '')
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript_text,
                            "role": "assistant",
                            "is_final": True
                        })
                        # Accumulate for CI session transcript
                        if ci_state["session_id"] and transcript_text:
                            async with ci_lock:
                                ci_state["transcript_parts"].append(("Assistant", transcript_text))
                                # HIGH-4: Cap memory at 500 entries
                                if len(ci_state["transcript_parts"]) > 500:
                                    logger.warning("Transcript buffer exceeded 500 entries, triggering early flush")
                                    ci_state["needs_flush"] = True

                    elif event_type == 'conversation.item.input_audio_transcription.completed':
                        # User speech transcription complete
                        transcript_text = data.get('transcript', '')
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript_text,
                            "role": "user",
                            "is_final": True
                        })
                        # Accumulate for CI session transcript
                        if ci_state["session_id"] and transcript_text:
                            async with ci_lock:
                                ci_state["transcript_parts"].append(("User", transcript_text))
                                # HIGH-4: Cap memory at 500 entries
                                if len(ci_state["transcript_parts"]) > 500:
                                    logger.warning("Transcript buffer exceeded 500 entries, triggering early flush")
                                    ci_state["needs_flush"] = True

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

                            # Emit CI-specific events for Aria mobile app real-time updates
                            if action_status == "success":
                                try:
                                    if func_name == "start_call_recording":
                                        ci_session_id = result.get("session_id")
                                        # Track active CI session for transcript accumulation
                                        async with ci_lock:
                                            ci_state["session_id"] = ci_session_id
                                            ci_state["transcript_parts"] = []
                                            ci_state["flushed_index"] = 0
                                            ci_state["needs_flush"] = False
                                        # P2: Cancel existing flush task before starting new one
                                        if ci_state.get("flush_task"):
                                            ci_state["flush_task"].cancel()
                                        ci_state["flush_task"] = asyncio.create_task(
                                            _flush_transcript_periodically()
                                        )
                                        logger.info(f"CI transcript accumulation started for session {ci_session_id}")
                                        await websocket.send_json({
                                            "type": "ci_session_started",
                                            "session_id": ci_session_id,
                                        })
                                    elif func_name == "stop_call_recording":
                                        # P2: Stop periodic flush
                                        if ci_state.get("flush_task"):
                                            ci_state["flush_task"].cancel()
                                            ci_state["flush_task"] = None
                                        # Save accumulated transcript before session closes
                                        async with ci_lock:
                                            ci_sid = ci_state["session_id"] or result.get("session_id")
                                            transcript_snapshot = list(ci_state["transcript_parts"])
                                        if ci_sid and transcript_snapshot:
                                            try:
                                                from services.voice_ci_bridge_service import VoiceCIBridgeService
                                                full_text = "\n".join(
                                                    f"[{role}]: {utterance}"
                                                    for role, utterance in transcript_snapshot
                                                )
                                                bridge = VoiceCIBridgeService(db, ws_organization_id, ws_user_id)
                                                save_result = await bridge.update_session_transcript(ci_sid, full_text)
                                                db.commit()
                                                logger.info(
                                                    f"CI transcript saved: {save_result.get('word_count', 0)} words "
                                                    f"for session {ci_sid}"
                                                )
                                            except Exception as save_err:
                                                logger.error(f"Failed to save CI transcript: {save_err}")
                                                try:
                                                    db.rollback()
                                                except Exception as _exc:  # noqa: BLE001
                                                    pass
                                        # P2: Cancel flush task before resetting state
                                        if ci_state.get("flush_task"):
                                            ci_state["flush_task"].cancel()
                                            ci_state["flush_task"] = None
                                        # Reset CI state under lock
                                        async with ci_lock:
                                            ci_state["session_id"] = None
                                            ci_state["transcript_parts"] = []
                                            ci_state["flushed_index"] = 0
                                            ci_state["needs_flush"] = False
                                        await websocket.send_json({
                                            "type": "ci_processing_complete",
                                            "session_id": result.get("session_id"),
                                        })
                                    elif func_name == "get_call_artifacts":
                                        await websocket.send_json({
                                            "type": "ci_artifact_generated",
                                            "artifacts": result.get("artifacts", []),
                                            "count": result.get("count", 0),
                                        })
                                except Exception as ci_evt_err:
                                    # CI event emission is non-critical; log and continue
                                    logger.warning(f"Failed to send CI event for {func_name}: {ci_evt_err}")

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
        # P2: Cancel periodic flush task on disconnect
        if ci_state.get("flush_task"):
            ci_state["flush_task"].cancel()
            ci_state["flush_task"] = None
        # Save any unsaved CI transcript before tearing down
        async with ci_lock:
            disconnect_sid = ci_state["session_id"]
            disconnect_parts = list(ci_state["transcript_parts"])
            ci_state["session_id"] = None
            ci_state["transcript_parts"] = []
            ci_state["flushed_index"] = 0
            ci_state["needs_flush"] = False
        if disconnect_sid and disconnect_parts:
            try:
                from services.voice_ci_bridge_service import VoiceCIBridgeService
                full_text = "\n".join(
                    f"[{role}]: {utterance}"
                    for role, utterance in disconnect_parts
                )
                bridge = VoiceCIBridgeService(db, ws_organization_id, ws_user_id)
                await bridge.update_session_transcript(disconnect_sid, full_text)
                db.commit()
                logger.info(f"CI transcript saved on disconnect for session {disconnect_sid}")
            except Exception as e:
                logger.error(f"Failed to save CI transcript on disconnect: {e}")
                try:
                    db.rollback()
                except Exception as _exc:  # noqa: BLE001
                    pass

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
