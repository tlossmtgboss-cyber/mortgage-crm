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
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/aria", tags=["aria"])


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

    state = await session_store.get_or_create(
        session_id=session_id,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        user_name=user.full_name,
        user_role=user.role,
    )

    # Send greeting
    from aria.core.context_loader import AriaContextLoader
    context_loader = AriaContextLoader()
    context = await context_loader.load_full(str(user.user_id))
    greeting = _build_greeting(user.full_name, context)
    await websocket.send_json({"type": "greeting", "content": greeting})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "message")
            user_content = msg.get("content", "")

            # Handle confirmation
            if msg_type == "confirm":
                confirmed = msg.get("value", False)
                if confirmed and state.get("phase") == "confirming":
                    await websocket.send_json({"type": "typing"})
                    state = {**state, "phase": "executing"}
                    state = await _run_graph_step(state, websocket)
                else:
                    await websocket.send_json({
                        "type": "done",
                        "content": "No problem — what would you like to change?"
                    })
                    state = {**state, "phase": "understanding"}
                continue

            # Handle new message
            if msg_type in ("message", "voice_transcript"):
                human_msg = HumanMessage(content=user_content)
                state = {**state, "messages": state.get("messages", []) + [human_msg]}

                if state.get("phase") == "slot_filling":
                    state = await _run_slot_answer(state, websocket)
                else:
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
        except Exception:
            pass


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


async def _run_slot_answer(state, websocket: WebSocket):
    """Parse user's answer to a slot question and continue."""
    from aria.core.conversation_engine import slot_answer_node, slot_fill_node, confirmation_node

    state = await slot_answer_node(state)

    if state.get("missing_slots"):
        state = await slot_fill_node(state)
        ai_msgs = [m for m in state.get("messages", []) if isinstance(m, AIMessage)]
        if ai_msgs:
            await websocket.send_json({"type": "done", "content": ai_msgs[-1].content})
    else:
        state = await confirmation_node(state)

    return state


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
