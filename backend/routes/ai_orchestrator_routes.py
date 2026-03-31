"""
AI Orchestrator Chat Routes
AI Chat powered by LangGraph AgentOrchestrator with 215 tools and streaming
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from collections import defaultdict
import logging
import json
import uuid
import time
import os
import tempfile
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai")


# =============================================================================
# RATE LIMITER — per-user, in-memory sliding window
# =============================================================================

# In-memory sliding window rate limiter.
# Intentionally in-memory for single-instance Railway deployment.
# For multi-instance, replace with Redis-backed limiter.
_rate_limit_store: Dict[str, list] = defaultdict(list)
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("AI_RATE_LIMIT_MAX", "15"))  # per-user requests
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AI_RATE_LIMIT_WINDOW", "60"))  # per window
RATE_LIMIT_ORG_MAX = int(os.getenv("AI_RATE_LIMIT_ORG_MAX", "100"))  # per-org requests


def _check_rate_limit(user_id: str, org_id: str = None) -> None:
    """
    Check per-user and per-organization rate limit using a sliding window.
    Raises HTTPException 429 if limit exceeded.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Per-user check
    timestamps = _rate_limit_store[user_id]
    _rate_limit_store[user_id] = [t for t in timestamps if t > window_start]

    if len(_rate_limit_store[user_id]) >= RATE_LIMIT_MAX_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - _rate_limit_store[user_id][0]))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s. Retry after {max(retry_after, 1)}s.",
            headers={"Retry-After": str(max(retry_after, 1))}
        )

    # Per-organization check
    if org_id:
        org_key = f"org:{org_id}"
        org_timestamps = _rate_limit_store[org_key]
        _rate_limit_store[org_key] = [t for t in org_timestamps if t > window_start]
        if len(_rate_limit_store[org_key]) >= RATE_LIMIT_ORG_MAX:
            raise HTTPException(
                status_code=429,
                detail="Organization rate limit exceeded. Please wait before sending more requests.",
                headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)}
            )
        _rate_limit_store[org_key].append(now)

    _rate_limit_store[user_id].append(now)


# =============================================================================
# INPUT SANITIZATION
# =============================================================================

# Max message length to prevent abuse
MAX_MESSAGE_LENGTH = int(os.getenv("AI_MAX_MESSAGE_LENGTH", "10000"))


def _sanitize_message(message: str) -> str:
    """
    Sanitize user message before sending to LLM.
    Strips HTML, neutralizes prompt injection patterns, and limits length.
    """
    if not message:
        return message

    try:
        from input_validation import sanitize_chat_input
        return sanitize_chat_input(message, max_length=MAX_MESSAGE_LENGTH)
    except ImportError:
        logger.warning("input_validation.sanitize_chat_input not available, using basic sanitization")

    # Fallback: basic HTML strip + length cap
    try:
        import nh3
        message = nh3.clean(message, tags=set())
    except ImportError:
        import re
        message = re.sub(r'<[^>]+>', '', message)

    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH]

    return message.strip()


def _sanitize_document_context(context: Optional[str]) -> Optional[str]:
    """
    Sanitize extracted document context before injecting into LLM prompt.
    Strips HTML, filters prompt injection patterns, and wraps in clear delimiters
    so LLM can distinguish document content from instructions.
    """
    if not context:
        return None

    # Strip HTML
    try:
        import nh3
        context = nh3.clean(context, tags=set())
    except ImportError:
        import re
        context = re.sub(r'<[^>]+>', '', context)

    # Filter prompt injection patterns from document content
    try:
        from input_validation import _INJECTION_REGEXES
        for pattern in _INJECTION_REGEXES:
            context = pattern.sub("[FILTERED]", context)
    except ImportError:
        import re
        injection_patterns = [
            r"(?i)ignore\s+(previous|all|above|prior)\s+instructions",
            r"(?i)you\s+are\s+now\s+a",
            r"(?i)system\s*prompt\s*:",
            r"(?i)new\s+instructions?\s*:",
            r"<\|.*?\|>",
        ]
        for pattern in injection_patterns:
            context = re.sub(pattern, "[FILTERED]", context)

    # Truncate if too long
    max_doc_length = 50000
    if len(context) > max_doc_length:
        context = context[:max_doc_length]

    # Wrap in clear delimiters to prevent prompt injection via document content
    return f"[DOCUMENT CONTENT START]\n{context}\n[DOCUMENT CONTENT END]"


def get_db_dep(request: Request = None):
    """Lazy database session dependency - yields a session then cleans up."""
    from db import get_db
    yield from get_db(request)


MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENT_CHARS = 50_000
SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".html"}
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/extract-document")
async def extract_document(
    file: UploadFile = File(...),
    current_user=Depends(current_user_flexible_dep)
):
    """
    Extract text from an uploaded document (PDF, DOCX, TXT, MD, HTML) or image.
    Returns extracted text for the frontend to attach as document context.
    """
    filename = file.filename or "unknown"
    file_ext = os.path.splitext(filename)[1].lower()

    if file_ext not in SUPPORTED_DOC_EXTENSIONS and file_ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(sorted(SUPPORTED_DOC_EXTENSIONS | SUPPORTED_IMAGE_EXTENSIONS))}"
        )

    # Read file content and check size
    content = await file.read()
    if len(content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 10 MB."
        )

    extracted_text = None
    tmp_path = None

    try:
        if file_ext in SUPPORTED_IMAGE_EXTENSIONS:
            # Use Claude vision API to extract text from image
            extracted_text = await _extract_text_from_image(content, file_ext)
        else:
            # Save to temp file for text extraction
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            from services.call_monitoring.guidelines_service import extract_text_from_document
            extracted_text = await extract_text_from_document(tmp_path, file_ext)
    except Exception as e:
        logger.error(f"Document extraction failed for {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to extract text from document")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from this document. The file may be empty, scanned, or corrupted."
        )

    truncated = len(extracted_text) > MAX_DOCUMENT_CHARS
    if truncated:
        extracted_text = extracted_text[:MAX_DOCUMENT_CHARS]

    return {
        "success": True,
        "filename": filename,
        "file_type": file_ext,
        "extracted_text": extracted_text,
        "char_count": len(extracted_text),
        "truncated": truncated,
    }


async def _extract_text_from_image(image_bytes: bytes, file_ext: str) -> str:
    """Use Claude vision API to extract text from an image."""
    import base64
    from anthropic import Anthropic

    media_type_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    media_type = media_type_map.get(file_ext, "image/png")
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                {"type": "text", "text": "Extract ALL text from this image. Return only the extracted text, preserving the original formatting and structure as closely as possible. If this is a document, include all content. If there is no readable text, respond with 'No text found in image.'"}
            ]
        }]
    )
    return response.content[0].text


@router.post("/langgraph-chat")
@router.post("/orchestrator-chat")
async def orchestrator_chat(
    request: Request,
    db: Session = Depends(get_db_dep),
    current_user = Depends(current_user_flexible_dep)
):
    """
    AI Chat powered by the LangGraph AgentOrchestrator with full tool execution.
    Routes messages to specialized agents (pipeline, compliance, leads, docs, etc.)
    and executes real CRM actions against the database.
    Accessible via both /langgraph-chat (used by AILandingPage) and /orchestrator-chat.
    """
    try:
        from conversation_memory_service import ConversationMemory as ConvMemory
        from agents.service import create_ai_agent_service

        request_start_time = time.time()

        # Rate limit check (per-user and per-org)
        user_id_str = str(getattr(current_user, 'id', 'unknown'))
        org_id_str = str(getattr(current_user, 'organization_id', '')) or None
        _check_rate_limit(user_id_str, org_id_str)

        data = await request.json()
        message = _sanitize_message(data.get("message", ""))
        session_id = data.get("session_id")
        document_context = _sanitize_document_context(data.get("document_context"))

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        if not session_id:
            session_id = str(uuid.uuid4())

        # Load conversation history
        try:
            conversation_history = ConvMemory.get_session_messages(db, session_id)
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
            conversation_history = []

        # Create the full agent service with all 215 tools
        service = await create_ai_agent_service(db, current_user, autonomous_mode=True)

        # Process through LangGraph orchestrator (document_context injected for this turn only)
        result = await service.process_message(message, conversation_history, document_context=document_context)

        # Save to conversation memory (non-fatal on failure)
        try:
            ConvMemory.save_message(db, session_id, current_user.id, "user", message)
            ConvMemory.save_message(db, session_id, current_user.id, "assistant", result.get("response", ""))
        except Exception as save_err:
            logger.warning(f"Failed to save conversation: {save_err}")

        response_time = time.time() - request_start_time

        return {
            "success": True,
            "response": result.get("response", ""),
            "session_id": session_id,
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
            "follow_up_suggestions": result.get("follow_up_suggestions", []),
            "processing_time_seconds": result.get("processing_time_seconds", round(response_time, 2)),
            "data_quality": result.get("data_quality"),
            "actions_executed": result.get("actions_executed", []),
            "actions_pending": result.get("actions_pending", []),
            "engine": "langgraph",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestrator chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/orchestrator-chat-stream")
async def orchestrator_chat_stream(
    request: Request,
    db: Session = Depends(get_db_dep),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Streaming AI Chat - sends response tokens as they're generated.
    Uses Server-Sent Events (SSE) for real-time streaming via the LangGraph agent.
    """
    # Rate limit check (per-user and per-org)
    user_id_str = str(getattr(current_user, 'id', 'unknown'))
    org_id_str = str(getattr(current_user, 'organization_id', '')) or None
    _check_rate_limit(user_id_str, org_id_str)

    data = await request.json()
    message = _sanitize_message(data.get("message", ""))
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    async def generate():
        try:
            from agents.service import create_ai_agent_service
            from conversation_memory_service import ConversationMemory as ConvMemory

            # Load conversation history
            try:
                conversation_history = ConvMemory.get_session_messages(db, session_id)
            except Exception as e:
                logger.warning(f"Failed to load conversation history in stream: {e}")
                conversation_history = []

            # Create the full agent service with all 215 tools
            service = await create_ai_agent_service(db, current_user, autonomous_mode=True)

            # Stream response through the agent
            full_response = ""
            async for chunk in service.process_message_stream(message, conversation_history):
                chunk_type = chunk.get("type")

                if chunk_type == "content":
                    content = chunk.get("content", "")
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"

                elif chunk_type == "tool_use":
                    yield f"data: {json.dumps({'tool_use': chunk.get('tool'), 'input': chunk.get('input', {})})}\n\n"

                elif chunk_type == "tool_result":
                    yield f"data: {json.dumps({'tool_result': chunk.get('tool'), 'result': chunk.get('result', {})})}\n\n"

                elif chunk_type == "done":
                    full_response = chunk.get("full_response", full_response)

                elif chunk_type == "error":
                    yield f"data: {json.dumps({'error': chunk.get('error', 'Unknown error')})}\n\n"

            # Send completion
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'engine': 'langgraph'})}\n\n"

            # Save conversation (non-fatal on failure)
            try:
                ConvMemory.save_message(db, session_id, current_user.id, "user", message)
                ConvMemory.save_message(db, session_id, current_user.id, "assistant", full_response)
            except Exception as e:
                logger.warning(f"Failed to save conversation in stream: {e}")

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': 'An error occurred processing your request.'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
