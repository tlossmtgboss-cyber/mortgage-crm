"""
Recruiting Chatbot API Routes

Public endpoints (no auth — candidates from landing pages):
  POST  /api/v1/recruit-platform/chat/{tenant_slug}/message
  GET   /api/v1/recruit-platform/chat/{tenant_slug}/session/{session_id}
  GET   /api/v1/recruit-platform/chat/embed/{tenant_slug}/widget.js

Admin endpoints (auth required):
  GET   /api/v1/recruit-platform/chat/sessions
  GET   /api/v1/recruit-platform/chat/sessions/{session_id}
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

chatbot_router = APIRouter(
    prefix="/api/v1/recruit-platform/chat",
    tags=["recruit-chatbot-public"],
)

chatbot_admin_router = APIRouter(
    prefix="/api/v1/recruit-platform/chat",
    tags=["recruit-chatbot-admin"],
)

MESSAGE_RATE_LIMIT = 20


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    visitor_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_org(tenant_slug: str, db: Session) -> dict:
    """Return {id, name} for the given tenant slug, or 404."""
    row = db.execute(
        text("SELECT id, name FROM organizations WHERE slug = :slug AND is_active = true"),
        {"slug": tenant_slug},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Organization '{tenant_slug}' not found")
    return {"id": row.id, "name": row.name}


def _get_or_create_session(
    session_id: Optional[str],
    org_id: int,
    visitor_id: Optional[str],
    db: Session,
) -> str:
    """Return an existing session id or create a new one."""
    if session_id:
        row = db.execute(
            text("SELECT id FROM recruit_chat_sessions WHERE id = :sid"),
            {"sid": session_id},
        ).fetchone()
        if row:
            return session_id

    # Create new session
    new_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO recruit_chat_sessions (id, organization_id, visitor_id)
            VALUES (:id, :org_id, :visitor_id)
        """),
        {"id": new_id, "org_id": org_id, "visitor_id": visitor_id},
    )
    db.commit()
    return new_id


def _save_message(session_id: str, org_id: int, role: str, content: str, db: Session) -> None:
    db.execute(
        text("""
            INSERT INTO recruit_chat_messages (session_id, organization_id, role, content)
            VALUES (:sid, :org_id, :role, :content)
        """),
        {"sid": session_id, "org_id": org_id, "role": role, "content": content},
    )
    db.execute(
        text("""
            UPDATE recruit_chat_sessions
            SET message_count = message_count + 1, last_message_at = NOW()
            WHERE id = :sid
        """),
        {"sid": session_id},
    )
    db.commit()


def _load_message_history(session_id: str, db: Session) -> list:
    """Load conversation history in OpenAI message format."""
    rows = db.execute(
        text("""
            SELECT role, content FROM recruit_chat_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
        """),
        {"sid": session_id},
    ).fetchall()
    return [{"role": r.role, "content": r.content} for r in rows]


def _try_create_candidate(
    org_id: int,
    collected_info: dict,
    session_id: str,
    db: Session,
) -> Optional[int]:
    """Attempt to insert into mm_candidates; return new id or None."""
    try:
        existing = db.execute(
            text(
                "SELECT id FROM mm_candidates "
                "WHERE organization_id = :org_id AND email = :email"
            ),
            {"org_id": org_id, "email": collected_info.get("email", "")},
        ).fetchone()
        if existing:
            return existing.id

        result = db.execute(
            text("""
                INSERT INTO mm_candidates
                    (organization_id, name, email, phone, status, source)
                VALUES (:org_id, :name, :email, :phone, 'new', 'chatbot')
                RETURNING id
            """),
            {
                "org_id": org_id,
                "name": collected_info.get("name", ""),
                "email": collected_info.get("email", ""),
                "phone": collected_info.get("phone", ""),
            },
        )
        candidate_id = result.scalar()
        db.execute(
            text(
                "UPDATE recruit_chat_sessions SET candidate_id = :cid WHERE id = :sid"
            ),
            {"cid": candidate_id, "sid": session_id},
        )
        db.commit()
        return candidate_id
    except Exception as e:
        logger.warning("_try_create_candidate: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@chatbot_router.post("/{tenant_slug}/message")
async def send_message(
    tenant_slug: str,
    body: ChatMessageRequest,
    db: Session = Depends(get_db),
):
    from agents.recruit_orchestrator import run_recruit_chat

    org = _resolve_org(tenant_slug, db)
    org_id = org["id"]
    org_name = org["name"]

    session_id = _get_or_create_session(
        body.session_id, org_id, body.visitor_id, db
    )

    # Rate limit: 20 messages per session
    count_row = db.execute(
        text("SELECT message_count FROM recruit_chat_sessions WHERE id = :sid"),
        {"sid": session_id},
    ).fetchone()
    if count_row and count_row.message_count >= MESSAGE_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Session message limit reached. Please start a new conversation.",
        )

    # Save user message
    _save_message(session_id, org_id, "user", body.message, db)

    # Load full history (excluding the message we just saved to avoid duplication)
    history = _load_message_history(session_id, db)
    # history now includes the user message — pass history minus last entry as
    # prior context; run_recruit_chat appends the new user_message itself.
    prior_history = history[:-1] if history else []

    result = await run_recruit_chat(
        session_id=session_id,
        org_id=org_id,
        org_name=org_name,
        user_message=body.message,
        message_history=prior_history,
        db=db,
    )

    assistant_response = result["response"]
    collected_info = result["collected_info"]

    # Save assistant response
    _save_message(session_id, org_id, "assistant", assistant_response, db)

    # Update collected contact info on session
    if collected_info:
        updates = {}
        if collected_info.get("name"):
            updates["collected_name"] = collected_info["name"]
        if collected_info.get("email"):
            updates["collected_email"] = collected_info["email"]
        if collected_info.get("phone"):
            updates["collected_phone"] = collected_info["phone"]
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            updates["sid"] = session_id
            db.execute(
                text(f"UPDATE recruit_chat_sessions SET {set_clause} WHERE id = :sid"),
                updates,
            )
            db.commit()

    # Create candidate record if we have enough info
    if result["should_create_application"]:
        _try_create_candidate(org_id, collected_info, session_id, db)

    return {
        "session_id": session_id,
        "response": assistant_response,
        "collected_info": collected_info,
    }


@chatbot_router.get("/{tenant_slug}/session/{session_id}")
async def get_session_history(
    tenant_slug: str,
    session_id: str,
    db: Session = Depends(get_db),
):
    org = _resolve_org(tenant_slug, db)

    session = db.execute(
        text(
            "SELECT id FROM recruit_chat_sessions "
            "WHERE id = :sid AND organization_id = :org_id"
        ),
        {"sid": session_id, "org_id": org["id"]},
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = db.execute(
        text("""
            SELECT role, content, created_at
            FROM recruit_chat_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
        """),
        {"sid": session_id},
    ).fetchall()

    return [
        {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@chatbot_router.get("/embed/{tenant_slug}/widget.js")
async def widget_js(tenant_slug: str):
    """Return the embeddable chat widget JavaScript."""
    js = f"""
(function() {{
  var TENANT_SLUG = {repr(tenant_slug)};
  var WIDGET_URL = 'https://recruit.perenniaai.com/recruit/chat-widget/' + TENANT_SLUG;

  // Create bubble container
  var container = document.createElement('div');
  container.id = 'perennia-chat-bubble';
  container.style.cssText = [
    'position:fixed',
    'bottom:24px',
    'right:24px',
    'z-index:999999',
    'display:flex',
    'flex-direction:column',
    'align-items:flex-end',
    'gap:8px',
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
  ].join(';');

  // Bubble button
  var bubble = document.createElement('button');
  bubble.title = 'Chat with us';
  bubble.style.cssText = [
    'width:60px',
    'height:60px',
    'border-radius:50%',
    'background:#2563eb',
    'border:none',
    'cursor:pointer',
    'box-shadow:0 4px 12px rgba(0,0,0,0.25)',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'transition:transform 0.2s'
  ].join(';');
  bubble.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';

  // Label
  var label = document.createElement('span');
  label.textContent = 'Chat with us';
  label.style.cssText = [
    'background:#1e293b',
    'color:#fff',
    'padding:4px 10px',
    'border-radius:12px',
    'font-size:13px',
    'font-weight:500',
    'white-space:nowrap',
    'box-shadow:0 2px 6px rgba(0,0,0,0.2)'
  ].join(';');

  // Chat iframe
  var iframe = null;
  var isOpen = false;

  function openChat() {{
    if (!iframe) {{
      iframe = document.createElement('iframe');
      iframe.src = WIDGET_URL;
      iframe.style.cssText = [
        'width:380px',
        'height:560px',
        'max-width:calc(100vw - 48px)',
        'max-height:calc(100vh - 100px)',
        'border:none',
        'border-radius:16px',
        'box-shadow:0 8px 32px rgba(0,0,0,0.2)',
        'background:#fff'
      ].join(';');
      container.insertBefore(iframe, bubble);
    }}
    iframe.style.display = 'block';
    label.style.display = 'none';
    isOpen = true;
  }}

  function closeChat() {{
    if (iframe) iframe.style.display = 'none';
    label.style.display = 'block';
    isOpen = false;
  }}

  bubble.addEventListener('click', function() {{
    if (isOpen) {{ closeChat(); }} else {{ openChat(); }}
  }});
  bubble.addEventListener('mouseover', function() {{
    bubble.style.transform = 'scale(1.1)';
  }});
  bubble.addEventListener('mouseout', function() {{
    bubble.style.transform = 'scale(1)';
  }});

  container.appendChild(label);
  container.appendChild(bubble);
  document.body.appendChild(container);
}})();
""".strip()

    return Response(content=js, media_type="application/javascript")


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@chatbot_admin_router.get("/sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id
    rows = db.execute(
        text("""
            SELECT id, visitor_id, candidate_id, started_at, last_message_at,
                   message_count, collected_name, collected_email, collected_phone
            FROM recruit_chat_sessions
            WHERE organization_id = :org_id
            ORDER BY last_message_at DESC
            LIMIT 200
        """),
        {"org_id": org_id},
    ).fetchall()

    return [
        {
            "session_id": r.id,
            "visitor_id": r.visitor_id,
            "candidate_id": r.candidate_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
            "message_count": r.message_count,
            "collected_name": r.collected_name,
            "collected_email": r.collected_email,
            "collected_phone": r.collected_phone,
        }
        for r in rows
    ]


@chatbot_admin_router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = current_user.organization_id

    session = db.execute(
        text("""
            SELECT id, visitor_id, candidate_id, started_at, last_message_at,
                   message_count, collected_name, collected_email, collected_phone, metadata
            FROM recruit_chat_sessions
            WHERE id = :sid AND organization_id = :org_id
        """),
        {"sid": session_id, "org_id": org_id},
    ).fetchone()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.execute(
        text("""
            SELECT role, content, created_at
            FROM recruit_chat_messages
            WHERE session_id = :sid
            ORDER BY created_at ASC
        """),
        {"sid": session_id},
    ).fetchall()

    return {
        "session_id": session.id,
        "visitor_id": session.visitor_id,
        "candidate_id": session.candidate_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
        "message_count": session.message_count,
        "collected_name": session.collected_name,
        "collected_email": session.collected_email,
        "collected_phone": session.collected_phone,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
