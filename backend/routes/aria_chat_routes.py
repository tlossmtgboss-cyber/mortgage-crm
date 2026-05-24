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


def _get_voice_memory(org_id: str = None):
    from aria.core.voice_memory import VoiceMemory
    return VoiceMemory(organization_id=org_id)


async def _load_voice_preferences(user_id: str, org_id: str = None) -> dict:
    """Load VoiceMemory preferences off the event loop. Returns {} on failure."""
    try:
        vm = _get_voice_memory(org_id=org_id)
        prefs = await asyncio.to_thread(vm.get_all_preferences, user_id)
        return prefs or {}
    except Exception as e:
        logger.warning(f"VoiceMemory load failed for user {user_id}, using defaults: {e}")
        return {}


async def _record_voice_interaction(user_id: str, intent: str = "session_start", org_id: str = None):
    """Record an interaction pattern in VoiceMemory without blocking."""
    try:
        vm = _get_voice_memory(org_id=org_id)
        from datetime import datetime, timezone
        hour = datetime.now(timezone.utc).hour
        if hour < 6:
            tod = "early_morning"
        elif hour < 12:
            tod = "morning"
        elif hour < 17:
            tod = "afternoon"
        else:
            tod = "evening"
        await asyncio.to_thread(vm.record_interaction_pattern, user_id, intent, tod)
    except Exception as e:
        logger.warning(f"VoiceMemory interaction record failed for user {user_id}: {e}")


async def _record_conversation_outcome(user_id: str, agent_id: str, intent: str, task_result: dict, success: bool):
    """Record conversation outcome as an AgentContextEvent for the learning pipeline."""
    try:
        def _write():
            from db import SessionLocal
            from database.models.agent_context import AgentContextEvent
            from datetime import datetime, timezone
            db = SessionLocal()
            try:
                event = AgentContextEvent(
                    agent_id=agent_id,
                    user_id=int(user_id),
                    event_type="conversation_outcome",
                    original_output={
                        "intent": intent,
                        "success": success,
                        "has_result": bool(task_result),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                db.add(event)
                db.commit()
            except Exception as e:
                logger.debug(f"Outcome recording failed: {e}")
                db.rollback()
            finally:
                db.close()
        await asyncio.to_thread(_write)
    except Exception as e:
        logger.debug(f"Outcome recording error: {e}")


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

    # Load voice preferences (non-blocking, graceful fallback to {})
    user_org_id = str(user.org_id) if user.org_id else None
    voice_prefs = await _load_voice_preferences(uid, org_id=user_org_id)

    state = await session_store.get_or_create(
        session_id=session_id,
        user_id=uid,
        org_id=str(user.org_id),
        user_name=resolved_name,
        user_role=user.role,
        user_email=getattr(user, "email", ""),
    )
    # Attach voice preferences to state so they flow through the graph
    state["voice_preferences"] = voice_prefs

    # Use preferred_name from memory for greeting if available
    greeting_name = voice_prefs.get("preferred_name") or resolved_name
    greeting = _build_greeting(greeting_name, context, voice_prefs.get("greeting_style", "casual"))
    await websocket.send_json({"type": "greeting", "content": greeting})

    # Record session start interaction (fire-and-forget)
    asyncio.create_task(_record_voice_interaction(uid, "session_start", org_id=user_org_id))

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

                # Record actual intent pattern for learning (fire-and-forget)
                resolved_intent = state.get("intent")
                if resolved_intent:
                    asyncio.create_task(_record_voice_interaction(uid, resolved_intent, org_id=user_org_id))

                # Only record outcome when a task actually completed (not during slot-filling)
                task_result = state.get("task_result")
                if task_result is not None:
                    asyncio.create_task(_record_conversation_outcome(
                        user_id=uid,
                        agent_id="aria",
                        intent=resolved_intent or "unknown",
                        task_result=task_result,
                        success=not bool(state.get("error")),
                    ))

                if state.get("phase") == "confirming" and state.get("confirmation_preview"):
                    await websocket.send_json({
                        "type": "confirmation_required",
                        "preview": state["confirmation_preview"],
                    })

                await session_store.save(session_id, state)

    except WebSocketDisconnect:
        logger.info(f"Aria WS disconnected: user={user.user_id} session={session_id}")
        await session_store.save(session_id, state)
        # Record session end (non-blocking, best-effort)
        asyncio.create_task(_record_voice_interaction(uid, "session_end", org_id=user_org_id))
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


def _build_greeting(user_name: str, context: Dict[str, Any], greeting_style: str = "casual") -> str:
    first_name = user_name.split()[0] if user_name else "there"
    active_loans = context.get("active_loan_count", 0)
    urgent_tasks = context.get("urgent_task_count", 0)

    from datetime import datetime
    from zoneinfo import ZoneInfo
    hour = datetime.now(ZoneInfo("America/New_York")).hour

    if greeting_style == "formal":
        time_greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        greeting = f"{time_greeting}, {first_name}. "
    elif greeting_style == "first_name_only":
        greeting = f"{first_name}, "
    else:
        greeting = f"Hey {first_name}! "

    if urgent_tasks > 0:
        greeting += f"You've got {urgent_tasks} urgent task{'s' if urgent_tasks > 1 else ''} and "
        greeting += f"{active_loans} active loan{'s' if active_loans != 1 else ''}. What do you need?"
    elif active_loans > 0:
        greeting += f"You have {active_loans} active loan{'s' if active_loans != 1 else ''} in your pipeline. What can I do for you?"
    else:
        greeting += "What can I help you with today?"

    return greeting


# ─── REST greeting ────────────────────────────────────────────────────────────


@router.get("/greeting")
async def aria_greeting(
    current_user=Depends(get_current_user),
):
    """Return a personalized Aria greeting for REST clients (mobile chat)."""
    uid = str(current_user.id)
    user_name = getattr(current_user, "full_name", None) or ""
    if not user_name:
        user_name = getattr(current_user, "first_name", None) or ""

    try:
        from aria.core.context_loader import AriaContextLoader
        context_loader = AriaContextLoader()
        context = await asyncio.wait_for(context_loader.load_full(uid), timeout=10.0)
    except Exception as e:
        logger.warning(f"Greeting context load failed for user {uid}: {e}")
        context = {"active_loan_count": 0, "urgent_task_count": 0}

    if not user_name:
        ctx_name = context.get("user_name", "")
        if ctx_name and not ctx_name.startswith("gAAAAA"):
            user_name = ctx_name

    # Use preferred_name from VoiceMemory if available
    greeting_org_id = str(getattr(current_user, "organization_id", "")) or None
    voice_prefs = await _load_voice_preferences(uid, org_id=greeting_org_id)
    greeting_name = voice_prefs.get("preferred_name") or user_name

    return {"greeting": _build_greeting(greeting_name, context, voice_prefs.get("greeting_style", "casual"))}


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

    # Load voice preferences for REST path (matching WebSocket behavior)
    rest_org_id = str(getattr(current_user, "organization_id", "")) or None
    voice_prefs = await _load_voice_preferences(str(current_user.id), org_id=rest_org_id)
    state["voice_preferences"] = voice_prefs

    state = {**state, "messages": state.get("messages", []) + [HumanMessage(content=req.message)]}
    new_state = await aria_graph.ainvoke(state)
    await session_store.save(sid, new_state)

    # Record actual intent pattern for learning (fire-and-forget)
    resolved_intent = new_state.get("intent")
    if resolved_intent:
        asyncio.create_task(_record_voice_interaction(str(current_user.id), resolved_intent, org_id=rest_org_id))

    # Only record outcome when a task actually completed (not during slot-filling)
    task_result = new_state.get("task_result")
    if task_result is not None:
        asyncio.create_task(_record_conversation_outcome(
            user_id=str(current_user.id),
            agent_id="aria",
            intent=resolved_intent or "unknown",
            task_result=task_result,
            success=not bool(new_state.get("error")),
        ))

    ai_messages = [m for m in new_state.get("messages", []) if isinstance(m, AIMessage)]
    response_text = ai_messages[-1].content if ai_messages else "Sorry, I couldn't process that."

    phase_val = new_state.get("phase")
    requires_confirmation = (
        getattr(phase_val, "value", phase_val) == "confirming"
    )

    return {
        "session_id": sid,
        "response": response_text,
        "phase": new_state.get("phase"),
        "requires_confirmation": requires_confirmation,
        "confirmation_preview": new_state.get("confirmation_preview"),
        "task_result": new_state.get("task_result"),
    }
