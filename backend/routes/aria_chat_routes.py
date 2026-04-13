"""
Aria Chat Routes
Perennia AI — Aria Conversation API

WebSocket endpoint for real-time streaming conversation with Aria,
plus a REST fallback for non-WebSocket environments.

Mobile/web client connects via WebSocket and sends JSON messages:
  { "type": "message", "content": "Send Mike's realtor a pre-approval" }
  { "type": "confirm", "value": true }

Aria streams responses back as JSON events:
  { "type": "typing" }
  { "type": "chunk", "content": "Here's what I'll send..." }
  { "type": "done", "content": "Full message" }
  { "type": "confirmation_required", "preview": "..." }
  { "type": "task_complete", "result": {...} }
  { "type": "error", "message": "..." }
"""

import json
import logging
import asyncio
import re
import time
import threading
from typing import Dict, Any, List, Tuple
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/aria", tags=["aria"])

# ─── WebSocket rate limiting ────────────────────────────────────────────────
# In-memory per-user message rate limiter: max 10 messages per 60-second window.
# Timestamps older than the window are pruned on each check.

WS_RATE_LIMIT_MAX = 10
WS_RATE_LIMIT_WINDOW = 60  # seconds

_ws_rate_buckets: Dict[str, List[float]] = {}
_ws_rate_lock = threading.Lock()

# Max tracked user keys before evicting oldest-activity entries
_WS_RATE_MAX_KEYS = 5_000


def _ws_rate_check(user_id: str) -> bool:
    """Return True if the message is allowed, False if rate-limited."""
    now = time.monotonic()
    cutoff = now - WS_RATE_LIMIT_WINDOW

    with _ws_rate_lock:
        # Lazy eviction when bucket count grows too large
        if len(_ws_rate_buckets) > _WS_RATE_MAX_KEYS:
            # Drop entries with no recent activity
            stale_keys = [
                k for k, ts_list in _ws_rate_buckets.items()
                if not ts_list or ts_list[-1] < cutoff
            ]
            for k in stale_keys:
                _ws_rate_buckets.pop(k, None)

        timestamps = _ws_rate_buckets.get(user_id, [])
        # Prune expired timestamps
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= WS_RATE_LIMIT_MAX:
            _ws_rate_buckets[user_id] = timestamps
            return False

        timestamps.append(now)
        _ws_rate_buckets[user_id] = timestamps
        return True


# ─── Input validation helpers ───────────────────────────────────────────────

WS_MAX_MESSAGE_LENGTH = 2000
_VALID_WS_TYPES = {"message", "confirm", "voice_transcript", "pong"}
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _get_session_store():
    from aria.core.session_store import AriaSessionStore
    return AriaSessionStore()


def _get_aria_graph():
    from aria.core.conversation_engine import get_aria_graph
    return get_aria_graph()


def _verify_ws_token(token: str):
    """Verify a JWT token for WebSocket auth (no Depends available in WS)."""
    try:
        from auth.tokens import _verify_secure_token
        payload = _verify_secure_token(token)
        if not payload:
            return None

        class _User:
            def __init__(self, p):
                self.id = p.get("sub") or p.get("user_id")
                self.user_id = self.id
                self.org_id = p.get("org_id") or p.get("organization_id", "")
                self.full_name = p.get("name", "")
                self.role = p.get("role", "user")
                self.organization_id = self.org_id

        return _User(payload)
    except Exception as e:
        logger.warning(f"WS token verification failed: {e}")
        return None


@router.websocket("/ws")
async def aria_websocket(
    websocket: WebSocket,
    token: str = Query(...),
):
    """Main WebSocket endpoint for Aria conversations."""
    user = _verify_ws_token(token)
    if not user:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    session_id = str(uuid4())
    session_store = _get_session_store()
    uid = str(user.user_id)

    state = await session_store.get_or_create(
        session_id=session_id,
        user_id=uid,
        org_id=str(user.org_id),
        user_name=user.full_name,
        user_role=user.role,
    )

    # Send greeting
    from aria.core.context_loader import AriaContextLoader
    context_loader = AriaContextLoader()
    context = await context_loader.load_full(uid)
    greeting = _build_greeting(user.full_name, context)
    await websocket.send_json({"type": "greeting", "content": greeting})

    # Start heartbeat background task (ping every 30s)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            # ── Validate JSON structure ──────────────────────────────────
            if not isinstance(msg, dict):
                await websocket.send_json({"type": "error", "message": "Message must be a JSON object"})
                continue

            msg_type = msg.get("type", "message")

            # Handle pong responses to our heartbeat pings
            if msg_type == "pong":
                continue

            # Validate message type
            if msg_type not in _VALID_WS_TYPES:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Invalid message type. Expected one of: message, confirm, voice_transcript"
                })
                continue

            # ── Rate limiting ────────────────────────────────────────────
            if not _ws_rate_check(uid):
                await websocket.send_json({
                    "type": "error",
                    "message": "Rate limit exceeded. Please wait before sending more messages."
                })
                continue

            # ── Validate content field ───────────────────────────────────
            user_content = msg.get("content", "")
            if not isinstance(user_content, str):
                await websocket.send_json({"type": "error", "message": "Content must be a string"})
                continue

            if len(user_content) > WS_MAX_MESSAGE_LENGTH:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Message too long. Maximum {WS_MAX_MESSAGE_LENGTH} characters."
                })
                continue

            # Strip HTML tags from content
            user_content = _HTML_TAG_RE.sub('', user_content)

            # Handle confirmation — convert to a HumanMessage and let the graph route it
            if msg_type == "confirm":
                confirmed = msg.get("value", False)
                user_content = "Yes, go ahead" if confirmed else "No, cancel that"

            # Handle all messages (including confirm converted above)
            if msg_type in ("message", "voice_transcript", "confirm"):
                human_msg = HumanMessage(content=user_content)
                state["messages"] = state.get("messages", []) + [human_msg]

                await websocket.send_json({"type": "typing"})
                state = await _run_graph_step(state, websocket)

                if state.get("phase") == "confirming" and state.get("confirmation_preview"):
                    await websocket.send_json({
                        "type": "confirmation_required",
                        "preview": state["confirmation_preview"],
                    })

                await session_store.save(session_id, state)

    except WebSocketDisconnect:
        logger.info(f"Aria WS disconnected: user={user.user_id} session={session_id}")
        await session_store.save(session_id, state)
    except Exception as e:
        logger.error(f"Aria WS error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": "Something went wrong. Try again?"})
        except Exception as send_err:
            logger.warning(f"Failed to send error message to WS client: {send_err}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def _heartbeat_loop(websocket: WebSocket):
    """Send a ping every 30 seconds to keep the connection alive and detect stale clients."""
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Heartbeat loop error: {e}")


async def _run_graph_step(state, websocket: WebSocket):
    """Run one step of the Aria LangGraph and stream the response."""
    aria_graph = _get_aria_graph()
    new_state = await aria_graph.ainvoke(state)

    ai_messages = [m for m in new_state.get("messages", []) if isinstance(m, AIMessage)]
    if ai_messages:
        content = ai_messages[-1].content
        chunk_size = 30
        for i in range(0, len(content), chunk_size):
            await websocket.send_json({"type": "chunk", "content": content[i:i+chunk_size]})
            await asyncio.sleep(0.02)
        await websocket.send_json({"type": "done", "content": content})

    if new_state.get("task_result"):
        await websocket.send_json({
            "type": "task_complete",
            "result": new_state["task_result"],
        })

    return new_state


def _build_greeting(user_name: str, context: Dict[str, Any]) -> str:
    first_name = user_name.split()[0] if user_name else "there"
    active_loans = context.get("active_loan_count", 0)
    urgent_tasks = context.get("urgent_task_count", 0)

    greeting = f"Hey {first_name}! "

    if urgent_tasks > 0:
        greeting += f"You've got {urgent_tasks} urgent task{'s' if urgent_tasks > 1 else ''} and "
        greeting += f"{active_loans} active loan{'s' if active_loans != 1 else ''}. What do you need?"
    elif active_loans > 0:
        greeting += f"You have {active_loans} active loan{'s' if active_loans != 1 else ''} in your pipeline. What can I do for you?"
    else:
        greeting += "What can I help you with today?"

    return greeting


# ─── REST fallback ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


@router.post("/chat")
async def aria_chat_rest(
    req: ChatRequest,
    current_user=Depends(get_current_user),
):
    """REST fallback for non-WebSocket environments."""
    session_store = _get_session_store()
    aria_graph = _get_aria_graph()

    sid = req.session_id or str(uuid4())
    state = await session_store.get_or_create(
        session_id=sid,
        user_id=str(current_user.id),
        org_id=str(getattr(current_user, "organization_id", "")),
        user_name=getattr(current_user, "full_name", ""),
        user_role=getattr(current_user, "role", "user"),
    )

    state = {**state, "messages": state.get("messages", []) + [HumanMessage(content=req.message)]}
    new_state = await aria_graph.ainvoke(state)
    await session_store.save(sid, new_state)

    ai_messages = [m for m in new_state.get("messages", []) if isinstance(m, AIMessage)]
    response_text = ai_messages[-1].content if ai_messages else "Sorry, I couldn't process that."

    return {
        "session_id": sid,
        "response": response_text,
        "phase": new_state.get("phase"),
        "requires_confirmation": str(new_state.get("phase")) == "confirming",
        "confirmation_preview": new_state.get("confirmation_preview"),
        "task_result": new_state.get("task_result"),
    }
