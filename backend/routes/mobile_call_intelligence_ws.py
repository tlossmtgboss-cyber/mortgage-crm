"""
Mobile Call Intelligence WebSocket

Real-time agent event streaming for the mobile frontend's call intelligence UI.

Two WebSocket endpoints:
1. /ws/call-intelligence/{session_id}  — Live agent events during a call
2. /ws/call-intelligence/watch         — Watch for new active calls for an LO

The mobile frontend (useCallIntelligence.js) connects here to receive structured
agent messages (note_taker, jr_loan_officer, auditor, receptionist) and can also
push transcript text into the session.

Architecture:
- Post-connect authentication (first message: {"type": "auth", "token": "..."})
- RLS tenant context set after auth
- Background polling loop reads agent_events + call_artifacts tables
- Maps backend agent types to frontend agent types
- Module-level ConnectionManager singleton for external push
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Mobile Call Intelligence WS"])

# Poll interval for new events/artifacts (seconds)
_POLL_INTERVAL = 0.5

# Streaming extraction: run after every N final transcript chunks
_EXTRACTION_CHUNK_THRESHOLD = 8
# Minimum seconds between extraction runs per session
_EXTRACTION_COOLDOWN_SECONDS = 15
# Per-session state for streaming extraction: {session_id: {chunk_count, last_extraction_time}}
_session_extraction_state: Dict[str, Dict] = {}

# ============================================================================
# AGENT TYPE MAPPING
# ============================================================================

# Backend agent_type -> frontend agent name
_AGENT_TYPE_MAP = {
    "scribe": "note_taker",
    "junior_lo": "jr_loan_officer",
    "underwriter": "auditor",
    "receptionist": "receptionist",
    "calculator": "jr_loan_officer",  # Calculator results surface via jr_loan_officer
    "marketing": "note_taker",        # Marketing artifacts surface via note_taker
}

# Artifact type -> (frontend_agent, frontend_event, payload builder)
# Each entry: (agent_name, event_name)
_ARTIFACT_EVENT_MAP = {
    # note_taker
    "summary": ("note_taker", "summary_updated"),
    "scribe_recap": ("note_taker", "summary_updated"),
    "stacked_note": ("note_taker", "summary_updated"),
    "borrower_story_note": ("note_taker", "topics_updated"),
    "story_theme": ("note_taker", "topics_updated"),
    "marketing_milestone": ("note_taker", "topics_updated"),
    # jr_loan_officer
    "intake_field": ("jr_loan_officer", "field_extracted"),
    "calculator_result": ("jr_loan_officer", "field_extracted"),
    "calculator_recommendation": ("jr_loan_officer", "field_extracted"),
    # auditor
    "risk_flag": ("auditor", "flag_raised"),
    "five_c_credit": ("auditor", "flag_raised"),
    "five_c_collateral": ("auditor", "flag_raised"),
    "five_c_capacity": ("auditor", "flag_raised"),
    "five_c_characteristics": ("auditor", "flag_raised"),
    "five_c_cash": ("auditor", "flag_raised"),
    "uw_review_item": ("auditor", "flag_raised"),
    "uw_note": ("auditor", "flag_raised"),
    "document_request": ("auditor", "document_request_sent"),
    "task": ("auditor", "task_created"),
    "action_item": ("auditor", "task_created"),
    # receptionist
    "scheduled_appointment": ("receptionist", "appointment_scheduled"),
    "follow_up_call": ("receptionist", "appointment_scheduled"),
    "calendar_action": ("receptionist", "action_taken"),
    "meeting_summary": ("receptionist", "action_taken"),
    "follow_up_draft": ("receptionist", "action_taken"),
}

# Agent event_type -> (frontend_agent, frontend_event)
_EVENT_TYPE_MAP = {
    "transcript_chunk": ("note_taker", "transcript_line"),
    "agent_started": None,  # Internal, skip
    "processing_started": None,
    "processing_completed": None,
    "session_created": None,
    "transcript_complete": None,
}


# ============================================================================
# CONNECTION MANAGER (module-level singleton)
# ============================================================================

class CallIntelligenceConnectionManager:
    """
    Manages WebSocket connections for call intelligence streaming.

    Two pools:
    - _connections: session_id -> list of websockets (live call event consumers)
    - _lo_watchers: lo_user_id (str) -> list of websockets (watch for new calls)

    Thread-safe for asyncio (single event loop). Import this singleton from
    other modules to push events externally:

        from routes.mobile_call_intelligence_ws import ci_connection_manager
        await ci_connection_manager.broadcast_to_session(session_id, msg)
    """

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lo_watchers: Dict[str, List[WebSocket]] = {}

    # -- Session connections --

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        logger.info(f"[CI-WS] Client connected to session {session_id} "
                     f"(total={len(self._connections[session_id])})")

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        conns = self._connections.get(session_id)
        if conns:
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                del self._connections[session_id]
        logger.info(f"[CI-WS] Client disconnected from session {session_id}")

    async def broadcast_to_session(self, session_id: str, message: dict) -> None:
        """Send a message to all clients watching a specific session."""
        conns = self._connections.get(session_id, [])
        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"[CI-WS] Failed to send to session {session_id}: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, session_id)

    # -- LO watcher connections --

    async def connect_watcher(self, websocket: WebSocket, lo_user_id: str) -> None:
        if lo_user_id not in self._lo_watchers:
            self._lo_watchers[lo_user_id] = []
        self._lo_watchers[lo_user_id].append(websocket)
        logger.info(f"[CI-WS] Watcher connected for LO {lo_user_id} "
                     f"(total={len(self._lo_watchers[lo_user_id])})")

    def disconnect_watcher(self, websocket: WebSocket, lo_user_id: str) -> None:
        watchers = self._lo_watchers.get(lo_user_id)
        if watchers:
            if websocket in watchers:
                watchers.remove(websocket)
            if not watchers:
                del self._lo_watchers[lo_user_id]
        logger.info(f"[CI-WS] Watcher disconnected for LO {lo_user_id}")

    async def notify_lo_watcher(self, lo_user_id: str, message: dict) -> None:
        """Notify all watchers for a given LO about a new/changed session."""
        watchers = self._lo_watchers.get(lo_user_id, [])
        dead: List[WebSocket] = []
        for ws in watchers:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"[CI-WS] Failed to notify watcher for LO {lo_user_id}: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect_watcher(ws, lo_user_id)

    @property
    def session_count(self) -> int:
        return len(self._connections)

    @property
    def watcher_count(self) -> int:
        return len(self._lo_watchers)


# Singleton — import from other modules
ci_connection_manager = CallIntelligenceConnectionManager()


# ============================================================================
# PAYLOAD BUILDERS
# ============================================================================

def _build_transcript_line_payload(event_row: dict) -> dict:
    """Build a note_taker/transcript_line payload from an agent_event row."""
    payload = event_row.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

    return {
        "id": str(event_row.get("id", uuid.uuid4())),
        "text": payload.get("text", payload.get("chunk", "")),
        "speaker": payload.get("speaker", "unknown"),
        "is_final": payload.get("is_final", True),
        "timestamp": event_row.get("event_time", datetime.now(timezone.utc).isoformat()),
    }


def _build_artifact_payload(artifact_row: dict) -> dict:
    """Build frontend payload from a call_artifacts row."""
    artifact_type = artifact_row.get("artifact_type", "")
    structured = artifact_row.get("structured_data", {})
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except (json.JSONDecodeError, TypeError):
            structured = {}

    mapping = _ARTIFACT_EVENT_MAP.get(artifact_type)
    if not mapping:
        return {}

    agent, event = mapping

    # Build payload based on event type
    if event == "summary_updated":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "summary": artifact_row.get("content", ""),
            },
        }

    elif event == "topics_updated":
        topics = structured.get("topics", [])
        if not topics and artifact_row.get("title"):
            topics = [artifact_row["title"]]
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "topics": topics,
            },
        }

    elif event == "field_extracted":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "borrower_name": structured.get("borrower_name"),
                "borrower_email": structured.get("borrower_email"),
                "field_name": structured.get("field_name", artifact_row.get("title", "")),
                "field_value": structured.get("proposed_value", structured.get("field_value")),
                "completion_percent": structured.get("completion_percent", 0),
                "fields_filled": structured.get("fields_filled", 0),
                "last_field_updated": structured.get("field_name", artifact_row.get("title", "")),
            },
        }

    elif event == "flag_raised":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "id": str(artifact_row.get("id", "")),
                "severity": artifact_row.get("priority", structured.get("severity", "medium")),
                "title": artifact_row.get("title", ""),
                "description": artifact_row.get("content", ""),
                "category": structured.get("category", structured.get("risk_category", artifact_type)),
            },
        }

    elif event == "document_request_sent":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "id": str(artifact_row.get("id", "")),
                "document_type": structured.get("document_type", artifact_row.get("title", "")),
                "reason": artifact_row.get("content", structured.get("reason", "")),
                "priority": artifact_row.get("priority", "medium"),
            },
        }

    elif event == "task_created":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "id": str(artifact_row.get("id", "")),
                "title": artifact_row.get("title", ""),
                "description": artifact_row.get("content", ""),
                "due_date": structured.get("due_date"),
                "priority": artifact_row.get("priority", "medium"),
            },
        }

    elif event == "appointment_scheduled":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "id": str(artifact_row.get("id", "")),
                "title": artifact_row.get("title", ""),
                "datetime": structured.get("datetime", structured.get("scheduled_time")),
                "borrower_invite_sent": structured.get("borrower_invite_sent", False),
            },
        }

    elif event == "action_taken":
        return {
            "agent": agent,
            "event": event,
            "payload": {
                "description": artifact_row.get("content", artifact_row.get("title", "")),
            },
        }

    return {}


def _build_event_message(event_row: dict) -> Optional[dict]:
    """Build a frontend message from an agent_events row."""
    event_type = event_row.get("event_type", "")
    agent_type = event_row.get("agent_type", "")

    # Check static mapping first
    if event_type in _EVENT_TYPE_MAP:
        mapping = _EVENT_TYPE_MAP[event_type]
        if mapping is None:
            return None  # Skip internal events
        frontend_agent, frontend_event = mapping

        if frontend_event == "transcript_line":
            return {
                "agent": frontend_agent,
                "event": frontend_event,
                "payload": _build_transcript_line_payload(event_row),
            }

    # For artifact_created events, the payload often contains artifact info
    if event_type in ("artifact_created", "artifacts_approved", "artifacts_executed"):
        payload = event_row.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        # These are batch status events — artifacts are polled separately
        return None

    # Map agent-specific events
    frontend_agent = _AGENT_TYPE_MAP.get(agent_type)
    if not frontend_agent:
        return None

    payload = event_row.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

    # Generic agent event passthrough
    return {
        "agent": frontend_agent,
        "event": event_type,
        "payload": payload,
    }


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def _get_db_session() -> Session:
    """Create a fresh DB session for WebSocket use (no FastAPI Depends)."""
    from database import SessionLocal
    return SessionLocal()


def _set_rls_context(db: Session, org_id: int) -> None:
    """Set RLS tenant context on a database session."""
    from database.tenant_mixin import set_tenant_context
    set_tenant_context(db, org_id)


def _validate_session_access(
    db: Session,
    session_id: str,
    user_id: int,
    org_id: int,
) -> bool:
    """
    Verify the user has access to this call session.
    Checks organization_id matches and the session exists.
    """
    result = db.execute(
        text("""
            SELECT id FROM call_sessions
            WHERE id = :session_id AND organization_id = :org_id
            LIMIT 1
        """),
        {"session_id": session_id, "org_id": org_id},
    ).fetchone()
    return result is not None


# ============================================================================
# POLLING LOOPS
# ============================================================================

async def _event_polling_loop(
    websocket: WebSocket,
    session_id: str,
    org_id: int,
    last_event_id: int = 0,
) -> None:
    """
    Poll agent_events for new events and send them to the WebSocket client.

    Runs until cancelled or the WebSocket disconnects.
    Uses a fresh DB session per poll cycle to avoid stale reads.
    """
    current_last_id = last_event_id

    while True:
        db = None
        try:
            db = _get_db_session()
            _set_rls_context(db, org_id)

            rows = db.execute(
                text("""
                    SELECT id, session_id, run_id, event_type, agent_type,
                           payload, event_time, transcript_timestamp_ms
                    FROM agent_events
                    WHERE session_id = :session_id
                      AND organization_id = :org_id
                      AND id > :last_id
                    ORDER BY id ASC
                    LIMIT 50
                """),
                {
                    "session_id": session_id,
                    "org_id": org_id,
                    "last_id": current_last_id,
                },
            ).fetchall()

            for row in rows:
                row_dict = {
                    "id": row[0],
                    "session_id": str(row[1]) if row[1] else None,
                    "run_id": str(row[2]) if row[2] else None,
                    "event_type": row[3],
                    "agent_type": row[4],
                    "payload": row[5],
                    "event_time": row[6].isoformat() if row[6] else None,
                    "transcript_timestamp_ms": row[7],
                }

                msg = _build_event_message(row_dict)
                if msg:
                    await websocket.send_json(msg)

                current_last_id = row[0]

        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f"[CI-WS] Event poll error for session {session_id}: {e}")
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(_POLL_INTERVAL)


async def _artifact_polling_loop(
    websocket: WebSocket,
    session_id: str,
    org_id: int,
) -> None:
    """
    Poll call_artifacts for new artifacts and map them to frontend agent events.

    Tracks seen artifact IDs to avoid duplicates. Uses a fresh DB session per
    poll cycle.
    """
    seen_artifact_ids: Set[str] = set()

    # Pre-load existing artifact IDs so we only send new ones
    db = None
    try:
        db = _get_db_session()
        _set_rls_context(db, org_id)
        existing = db.execute(
            text("""
                SELECT id FROM call_artifacts
                WHERE session_id = :session_id AND organization_id = :org_id
            """),
            {"session_id": session_id, "org_id": org_id},
        ).fetchall()
        for row in existing:
            seen_artifact_ids.add(str(row[0]))
    except Exception as e:
        logger.error(f"[CI-WS] Failed to pre-load artifacts for {session_id}: {e}")
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass

    while True:
        db = None
        try:
            db = _get_db_session()
            _set_rls_context(db, org_id)

            rows = db.execute(
                text("""
                    SELECT id, session_id, run_id, artifact_type, title, content,
                           structured_data, approval_status, confidence,
                           source_evidence, priority, created_at
                    FROM call_artifacts
                    WHERE session_id = :session_id
                      AND organization_id = :org_id
                    ORDER BY created_at ASC
                """),
                {"session_id": session_id, "org_id": org_id},
            ).fetchall()

            for row in rows:
                artifact_id = str(row[0])
                if artifact_id in seen_artifact_ids:
                    continue

                seen_artifact_ids.add(artifact_id)

                row_dict = {
                    "id": artifact_id,
                    "session_id": str(row[1]) if row[1] else None,
                    "run_id": str(row[2]) if row[2] else None,
                    "artifact_type": row[3],
                    "title": row[4],
                    "content": row[5],
                    "structured_data": row[6],
                    "approval_status": row[7],
                    "confidence": float(row[8]) if row[8] is not None else None,
                    "source_evidence": row[9],
                    "priority": row[10],
                    "created_at": row[11].isoformat() if row[11] else None,
                }

                msg = _build_artifact_payload(row_dict)
                if msg:
                    await websocket.send_json(msg)

        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f"[CI-WS] Artifact poll error for session {session_id}: {e}")
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(_POLL_INTERVAL)


async def _watch_polling_loop(
    websocket: WebSocket,
    lo_user_id: str,
    org_id: int,
) -> None:
    """
    Poll for active call sessions belonging to an LO and notify the watcher.

    Sends a message whenever a new active session appears or a session status changes.
    """
    known_sessions: Dict[str, str] = {}  # session_id -> status

    while True:
        db = None
        try:
            db = _get_db_session()
            _set_rls_context(db, org_id)

            rows = db.execute(
                text("""
                    SELECT id, status, capture_mode, started_at, duration_seconds,
                           lead_id, loan_id, full_transcript
                    FROM call_sessions
                    WHERE user_id = :user_id
                      AND organization_id = :org_id
                      AND status IN ('active', 'processing', 'review_pending')
                    ORDER BY started_at DESC
                    LIMIT 20
                """),
                {"user_id": lo_user_id, "org_id": org_id},
            ).fetchall()

            current_ids = set()
            for row in rows:
                sid = str(row[0])
                current_ids.add(sid)
                row_status = row[1]

                prev_status = known_sessions.get(sid)
                if prev_status != row_status:
                    known_sessions[sid] = row_status
                    transcript_preview = ""
                    if row[7]:
                        transcript_preview = row[7][:200]

                    await websocket.send_json({
                        "type": "session_update",
                        "session_id": sid,
                        "status": row_status,
                        "capture_mode": row[2],
                        "started_at": row[3].isoformat() if row[3] else None,
                        "duration_seconds": row[4],
                        "lead_id": str(row[5]) if row[5] else None,
                        "loan_id": str(row[6]) if row[6] else None,
                        "transcript_preview": transcript_preview,
                    })

            # Notify about ended sessions
            ended = set(known_sessions.keys()) - current_ids
            for sid in ended:
                await websocket.send_json({
                    "type": "session_ended",
                    "session_id": sid,
                })
                del known_sessions[sid]

        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f"[CI-WS] Watch poll error for LO {lo_user_id}: {e}")
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(2.0)  # Watch polling is less latency-sensitive


# ============================================================================
# TRANSCRIPT INGESTION
# ============================================================================

async def _handle_transcript_message(
    session_id: str,
    org_id: int,
    data: dict,
) -> None:
    """
    Accept a transcript chunk from the mobile client and feed it into the
    call session pipeline (append to call_sessions.full_transcript and create
    an agent_event).
    """
    chunk_text = data.get("text", "").strip()
    speaker = data.get("speaker", "unknown")
    timestamp_ms = data.get("timestamp_ms")
    is_final = data.get("is_final", True)

    if not chunk_text:
        return

    db = None
    try:
        db = _get_db_session()
        _set_rls_context(db, org_id)

        # Append transcript text
        word_count = len(chunk_text.split())
        db.execute(
            text("""
                UPDATE call_sessions
                SET full_transcript = COALESCE(full_transcript, '') || :chunk,
                    transcript_state = 'partial',
                    transcript_word_count = COALESCE(transcript_word_count, 0) + :word_count,
                    updated_at = NOW()
                WHERE id = :session_id AND organization_id = :org_id
            """),
            {
                "session_id": session_id,
                "chunk": chunk_text + "\n",
                "word_count": word_count,
                "org_id": org_id,
            },
        )

        # Log transcript event
        db.execute(
            text("""
                INSERT INTO agent_events (
                    session_id, event_type, agent_type, payload,
                    transcript_timestamp_ms, organization_id
                ) VALUES (
                    :session_id, 'transcript_chunk', 'scribe', :payload,
                    :timestamp_ms, :org_id
                )
            """),
            {
                "session_id": session_id,
                "payload": json.dumps({
                    "text": chunk_text,
                    "speaker": speaker,
                    "is_final": is_final,
                    "word_count": word_count,
                }),
                "timestamp_ms": timestamp_ms,
                "org_id": org_id,
            },
        )
        db.commit()

        # Trigger streaming extraction on final chunks
        if is_final:
            try:
                await _maybe_trigger_streaming_extraction(session_id, org_id)
            except Exception as ext_err:
                logger.debug(f"[CI-WS] Streaming extraction trigger failed: {ext_err}")

    except Exception as e:
        logger.error(f"[CI-WS] Failed to ingest transcript for session {session_id}: {e}")
        if db:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


# ============================================================================
# STREAMING EXTRACTION (real-time field updates during active calls)
# ============================================================================

async def _maybe_trigger_streaming_extraction(session_id: str, org_id: int) -> None:
    """
    Check if enough transcript has accumulated to run a lightweight extraction.

    Tracks final-chunk count per session and runs the unified extractor every
    _EXTRACTION_CHUNK_THRESHOLD final chunks, respecting _EXTRACTION_COOLDOWN_SECONDS.
    Pushes jr_loan_officer/field_extracted events via the connection manager.
    """
    state = _session_extraction_state.get(session_id)
    if not state:
        _session_extraction_state[session_id] = {
            "chunk_count": 1,
            "last_extraction_at": 0.0,
            "fields_seen": {},
        }
        return

    state["chunk_count"] = state.get("chunk_count", 0) + 1

    # Check thresholds
    import time
    now = time.monotonic()
    if state["chunk_count"] < _EXTRACTION_CHUNK_THRESHOLD:
        return
    if (now - state.get("last_extraction_at", 0)) < _EXTRACTION_COOLDOWN_SECONDS:
        return

    # Reset counters
    state["chunk_count"] = 0
    state["last_extraction_at"] = now

    # Run extraction in background to avoid blocking the WebSocket
    asyncio.create_task(_run_streaming_extraction(session_id, org_id, state))


async def _run_streaming_extraction(
    session_id: str, org_id: int, state: dict
) -> None:
    """
    Read the accumulated transcript, run a lightweight unified extraction,
    and push new field discoveries as jr_loan_officer/field_extracted events.
    """
    db = None
    try:
        db = _get_db_session()
        _set_rls_context(db, org_id)

        # Get current transcript
        row = db.execute(
            text("""
                SELECT full_transcript, loan_id, lead_id
                FROM call_sessions
                WHERE id = :sid AND organization_id = :org_id
            """),
            {"sid": session_id, "org_id": org_id},
        ).fetchone()

        if not row or not row[0]:
            return

        transcript = row[0]
        loan_id = row[1]
        lead_id = row[2]

        # Load existing borrower data for context
        existing_data = {}
        if loan_id:
            try:
                loan_row = db.execute(
                    text("""
                        SELECT borrower_name, borrower_email, borrower_phone,
                               loan_type, amount, purchase_price, property_address,
                               credit_score
                        FROM loans WHERE id = :lid AND organization_id = :org_id
                    """),
                    {"lid": loan_id, "org_id": org_id},
                ).fetchone()
                if loan_row:
                    existing_data = {
                        k: v for k, v in {
                            "borrower_name": loan_row[0],
                            "loan_type": loan_row[3],
                            "loan_amount": float(loan_row[4]) if loan_row[4] else None,
                            "purchase_price": float(loan_row[5]) if loan_row[5] else None,
                            "property_address": loan_row[6],
                            "credit_score": loan_row[7],
                        }.items() if v is not None
                    }
            except Exception:
                pass
        elif lead_id:
            try:
                lead_row = db.execute(
                    text("""
                        SELECT first_name, last_name, email, phone, credit_score,
                               annual_income, loan_amount, property_type
                        FROM leads WHERE id = :lid AND organization_id = :org_id
                    """),
                    {"lid": lead_id, "org_id": org_id},
                ).fetchone()
                if lead_row:
                    existing_data = {
                        k: v for k, v in {
                            "borrower_name": f"{lead_row[0] or ''} {lead_row[1] or ''}".strip(),
                            "email": lead_row[2],
                            "phone": lead_row[3],
                            "credit_score": lead_row[4],
                            "annual_income": float(lead_row[5]) if lead_row[5] else None,
                            "loan_amount": float(lead_row[6]) if lead_row[6] else None,
                            "property_type": lead_row[7],
                        }.items() if v is not None
                    }
            except Exception:
                pass

        db.close()
        db = None

        # Run unified extraction
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest

        db2 = _get_db_session()
        try:
            _set_rls_context(db2, org_id)
            processor = CallIntelligenceProcessor(db2)
            ci_request = CallIntelligenceRequest(
                call_id=f"streaming_{session_id}_{int(datetime.now(timezone.utc).timestamp())}",
                loan_id=int(loan_id) if loan_id else None,
                organization_id=org_id,
                transcript=transcript,
                existing_borrower_data=existing_data,
            )

            response = await processor.process_transcript(ci_request)

            if not response.success:
                logger.debug(f"[CI-WS] Streaming extraction failed for {session_id}")
                return

            # Collect all extracted fields across categories
            fields_seen = state.get("fields_seen", {})
            new_fields = {}
            total_fields = 0
            all_categories = [
                ("identity", response.identity_extractions),
                ("address", response.address_extractions),
                ("employment", response.employment_extractions),
                ("income", response.income_extractions),
                ("assets", response.assets_extractions),
                ("liabilities", response.liabilities_extractions),
                ("declarations", response.declarations_extractions),
                ("intent", response.intent_extractions),
            ]

            for category, extractions in all_categories:
                if not extractions:
                    continue
                for field_name, value in extractions.items():
                    if value is None:
                        continue
                    total_fields += 1
                    field_key = f"{category}.{field_name}"
                    prev_value = fields_seen.get(field_key)
                    actual_value = value
                    if isinstance(value, dict):
                        actual_value = value.get("value", value)
                    if str(actual_value) != str(prev_value):
                        new_fields[field_key] = actual_value
                        fields_seen[field_key] = str(actual_value)

            state["fields_seen"] = fields_seen

            if not new_fields:
                return

            # Map extracted fields to the 22-field schema the frontend expects
            _FRONTEND_FIELD_MAP = {
                "identity.first_name": "borrower_name",
                "identity.last_name": "borrower_name",
                "identity.email": "borrower_email",
                "identity.phone": "borrower_phone",
                "identity.date_of_birth": "borrower_dob",
                "identity.marital_status": "marital_status",
                "employment.employer_name": "employer_name",
                "employment.employment_type": "employment_type",
                "income.annual_salary": "annual_income",
                "employment.years_at_job": "years_employed",
                "intent.loan_type": "loan_type",
                "intent.loan_purpose": "loan_purpose",
                "address.purchase_price": "purchase_price",
                "intent.down_payment": "down_payment_amount",
                "address.property_type": "property_type",
                "address.property_use": "property_use",
                "identity.credit_score": "estimated_credit_score",
                "liabilities.monthly_debt": "monthly_debt",
                "declarations.bankruptcy": "bankruptcy_history",
                "intent.timeline": "target_close_date",
                "intent.preapproval_status": "pre_approval_needed",
            }

            payload_fields = {}
            last_updated = None
            for field_key, value in new_fields.items():
                frontend_key = _FRONTEND_FIELD_MAP.get(field_key)
                if frontend_key:
                    actual_val = value.get("value") if isinstance(value, dict) else value
                    payload_fields[frontend_key] = actual_val
                    last_updated = frontend_key

            if not payload_fields and not new_fields:
                return

            # Push field_extracted event to all connected clients
            payload_fields["completion_percent"] = min(
                round((total_fields / 22) * 100), 100
            )
            payload_fields["fields_filled"] = min(total_fields, 22)
            payload_fields["last_field_updated"] = last_updated or next(iter(new_fields))

            message = {
                "agent": "jr_loan_officer",
                "event": "field_extracted",
                "payload": payload_fields,
            }
            await ci_connection_manager.broadcast_to_session(session_id, message)

            logger.info(
                f"[CI-WS] Streaming extraction pushed {len(new_fields)} new fields "
                f"for session {session_id}"
            )

        finally:
            db2.close()

    except Exception as e:
        logger.warning(f"[CI-WS] Streaming extraction error for {session_id}: {e}")
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _cleanup_extraction_state(session_id: str) -> None:
    """Remove per-session extraction state on disconnect."""
    _session_extraction_state.pop(session_id, None)


# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================

@router.websocket("/ws/call-intelligence/{session_id}")
async def call_intelligence_ws(websocket: WebSocket, session_id: str):
    """
    Live agent event stream for a specific call session.

    Protocol:
    1. Server accepts the WebSocket
    2. Client sends: {"type": "auth", "token": "<JWT>"}
    3. Server validates, sets RLS, confirms with {"type": "connected", ...}
    4. Server starts pushing agent events from polling loops
    5. Client may send:
       - {"type": "ping"}                -> {"type": "pong"}
       - {"type": "transcript", ...}     -> ingested into session
       - {"type": "stop"}                -> server closes
    """
    from utils.websocket_auth import authenticate_websocket_post_connect

    await websocket.accept()

    db = None
    event_task = None
    artifact_task = None

    try:
        # ---- Authentication (post-connect) ----
        db = _get_db_session()
        user, auth_error = await authenticate_websocket_post_connect(websocket, db)

        if not user:
            logger.warning(f"[CI-WS] Auth failed for session {session_id}: {auth_error}")
            await websocket.send_json({
                "type": "error",
                "message": auth_error or "Authentication required",
            })
            await websocket.close(code=4001, reason="Authentication required")
            return

        org_id = getattr(user, "organization_id", None)
        if not org_id:
            await websocket.send_json({
                "type": "error",
                "message": "No organization context",
            })
            await websocket.close(code=4002, reason="No organization context")
            return

        # Set RLS context for the auth session
        try:
            _set_rls_context(db, org_id)
        except Exception as e:
            logger.error(f"[CI-WS] Failed to set RLS context: {e}")

        # ---- Validate session access ----
        if not _validate_session_access(db, session_id, user.id, org_id):
            await websocket.send_json({
                "type": "error",
                "message": "Session not found or access denied",
            })
            await websocket.close(code=4003, reason="Session not found")
            return

        # Close the auth DB session — polling loops create their own
        db.close()
        db = None

        # ---- Register connection ----
        await ci_connection_manager.connect(websocket, session_id)

        # ---- Send connection confirmation ----
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "user_id": user.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"[CI-WS] User {user.id} connected to session {session_id}")

        # ---- Start background polling tasks ----
        event_task = asyncio.create_task(
            _event_polling_loop(websocket, session_id, org_id)
        )
        artifact_task = asyncio.create_task(
            _artifact_polling_loop(websocket, session_id, org_id)
        )

        # ---- Main receive loop ----
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "transcript":
                await _handle_transcript_message(session_id, org_id, data)

            elif msg_type == "stop":
                logger.info(f"[CI-WS] Client requested stop for session {session_id}")
                break

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info(f"[CI-WS] Client disconnected from session {session_id}")
    except asyncio.CancelledError:
        logger.info(f"[CI-WS] Connection cancelled for session {session_id}")
    except Exception as e:
        logger.error(f"[CI-WS] Unexpected error for session {session_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error",
            })
        except Exception:
            pass
    finally:
        # Cancel polling tasks
        for task in (event_task, artifact_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # Clean up connection manager and streaming extraction state
        ci_connection_manager.disconnect(websocket, session_id)
        _cleanup_extraction_state(session_id)

        # Close DB session if still open
        if db:
            try:
                db.close()
            except Exception:
                pass

        # Close WebSocket if still open
        try:
            await websocket.close()
        except Exception:
            pass

        logger.info(f"[CI-WS] Session {session_id} connection fully closed")


@router.websocket("/ws/call-intelligence/watch")
async def call_intelligence_watch_ws(websocket: WebSocket):
    """
    Watch for new active call sessions for a specific LO.

    The mobile app connects here to know when a new call starts so it can
    open the call intelligence panel proactively.

    Query param: lo_user_id (passed via first auth message or URL)

    Protocol:
    1. Server accepts the WebSocket
    2. Client sends: {"type": "auth", "token": "<JWT>"}
    3. Server validates, resolves LO user, confirms with {"type": "watching", ...}
    4. Server polls call_sessions and sends session_update / session_ended messages
    5. Client may send:
       - {"type": "ping"}  -> {"type": "pong"}
       - {"type": "stop"}  -> server closes
    """
    from utils.websocket_auth import authenticate_websocket_post_connect

    await websocket.accept()

    db = None
    watch_task = None
    lo_user_id = None

    try:
        # ---- Authentication ----
        db = _get_db_session()
        user, auth_error = await authenticate_websocket_post_connect(websocket, db)

        if not user:
            logger.warning(f"[CI-WS] Watch auth failed: {auth_error}")
            await websocket.send_json({
                "type": "error",
                "message": auth_error or "Authentication required",
            })
            await websocket.close(code=4001, reason="Authentication required")
            return

        org_id = getattr(user, "organization_id", None)
        if not org_id:
            await websocket.send_json({
                "type": "error",
                "message": "No organization context",
            })
            await websocket.close(code=4002, reason="No organization context")
            return

        # Determine which LO to watch — prefer query param, fall back to auth user
        lo_user_id_param = websocket.query_params.get("lo_user_id")
        lo_user_id = lo_user_id_param or str(user.id)

        # Close auth DB session — watch loop creates its own
        db.close()
        db = None

        # ---- Register watcher ----
        await ci_connection_manager.connect_watcher(websocket, lo_user_id)

        await websocket.send_json({
            "type": "watching",
            "lo_user_id": lo_user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"[CI-WS] User {user.id} watching calls for LO {lo_user_id}")

        # ---- Start watch polling ----
        watch_task = asyncio.create_task(
            _watch_polling_loop(websocket, lo_user_id, org_id)
        )

        # ---- Main receive loop ----
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "stop":
                logger.info(f"[CI-WS] Watcher stop requested for LO {lo_user_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"[CI-WS] Watcher disconnected for LO {lo_user_id}")
    except asyncio.CancelledError:
        logger.info(f"[CI-WS] Watcher cancelled for LO {lo_user_id}")
    except Exception as e:
        logger.error(f"[CI-WS] Watcher error for LO {lo_user_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error",
            })
        except Exception:
            pass
    finally:
        if watch_task and not watch_task.done():
            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass

        if lo_user_id:
            ci_connection_manager.disconnect_watcher(websocket, lo_user_id)

        if db:
            try:
                db.close()
            except Exception:
                pass

        try:
            await websocket.close()
        except Exception:
            pass

        logger.info(f"[CI-WS] Watcher for LO {lo_user_id} fully closed")
