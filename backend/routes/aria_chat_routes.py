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
    """Verify JWT and extract claims. DB enrichment happens in _enrich_ws_user."""
    try:
        from auth.tokens import verify_access_token
        payload = verify_access_token(token)
        if not payload:
            return None

        class _User:
            pass

        u = _User()
        u.id = payload.get("user_id") or payload.get("sub", "")
        u.user_id = u.id
        u.org_id = str(payload.get("tenant_id") or payload.get("org_id") or payload.get("organization_id", ""))
        u.organization_id = u.org_id
        u.full_name = ""
        u.email = payload.get("sub", "")
        u.role = "user"
        return u
    except Exception as e:
        logger.warning(f"WS token verification failed: {e}")
        return None


async def _enrich_ws_user(user):
    """Look up the real User row in a thread to avoid blocking the event loop."""
    def _db_lookup():
        from db import SessionLocal
        from database.models import User as UserModel
        db = SessionLocal()
        try:
            row = db.query(UserModel).filter(UserModel.email == user.email).first() if user.email else None
            if row:
                return {
                    "full_name": row.full_name or "",
                    "email": row.email or user.email,
                    "role": getattr(row, "role", "user") or "user",
                    "id": row.id,
                    "org_id": str(getattr(row, "organization_id", "") or ""),
                }
        finally:
            db.close()
        return None

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_db_lookup), timeout=5.0)
        if result:
            user.full_name = result["full_name"]
            user.email = result["email"]
            user.role = result["role"]
            user.id = result["id"]
            user.user_id = result["id"]
            if not user.org_id:
                user.org_id = result["org_id"]
                user.organization_id = result["org_id"]
    except Exception as e:
        logger.warning(f"WS user DB enrichment failed, using JWT claims: {e}")


@router.websocket("/ws")
async def aria_websocket(
    websocket: WebSocket,
    token: str = Query(None),
):
    """Main WebSocket endpoint for Aria conversations.

    Security: Token sent as first message after connect (not in URL query string)
    to avoid leaking JWT into server/proxy access logs and browser history.
    Backwards compatible: old clients with ?token= query param still work.
    """
    # If no token in URL, accept first and wait for auth message
    if not token:
        await websocket.accept()
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("type") == "auth":
                token = msg.get("token", "")
        except (asyncio.TimeoutError, Exception):
            pass
        if not token:
            await websocket.send_json({"type": "error", "message": "Authentication required"})
            await websocket.close(code=4001)
            return

    user = _verify_ws_token(token)
    if not user:
        try:
            await websocket.close(code=4001)
        except RuntimeError:
            pass
        return

    # Enrich user with DB data (full_name, email) without blocking event loop
    await _enrich_ws_user(user)

    # Accept if not already accepted (legacy path with token in URL)
    if websocket.query_params.get("token"):
        await websocket.accept()
    session_id = str(uuid4())
    session_store = _get_session_store()
    uid = str(user.user_id)

    # Load pipeline context (also returns user_name from DB as fallback)
    try:
        from aria.core.context_loader import AriaContextLoader
        context_loader = AriaContextLoader()
        context = await asyncio.wait_for(context_loader.load_full(uid), timeout=10.0)
    except Exception as e:
        logger.warning(f"Context load failed for user {uid}: {e}")
        context = {"active_loan_count": 0, "urgent_task_count": 0}

    # Use DB-resolved full_name; fall back to context loader's user_name
    resolved_name = user.full_name or context.get("user_name", "")

    state = await session_store.get_or_create(
        session_id=session_id,
        user_id=uid,
        org_id=str(user.org_id),
        user_name=resolved_name,
        user_role=user.role,
        user_email=getattr(user, "email", ""),
    )

    greeting = _build_greeting(resolved_name, context)
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
    try:
        new_state = await asyncio.wait_for(aria_graph.ainvoke(state), timeout=45.0)
    except asyncio.TimeoutError:
        logger.error("Aria graph invocation timed out after 45s")
        await websocket.send_json({"type": "error", "message": "Response took too long. Try a shorter message?"})
        return state
    except Exception as e:
        logger.error(f"Aria graph error: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": "Something went wrong. Try again?"})
        return state

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
        user_email=getattr(current_user, "email", ""),
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
