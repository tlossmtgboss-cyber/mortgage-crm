"""
Voice Co-Presenter Routes
REST and WebSocket endpoints for the AI Voice Co-Presenter feature in video conferences.
"""

import os
import json
import logging
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, UploadFile, File, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models.voice_copresenter_models import (
    # Enums
    TabType, AIMode, VideoProvider, RateSheetStatus, PendingActionStatus,
    # Call Session
    CallSessionCreate, CallSessionUpdate, CallSessionResponse,
    # Rate Sheet
    RateSheetCreate, RateSheetResponse, RateLadderRequest, RateLadderResponse, RateRowResponse,
    # Scenario
    ScenarioCreate, ScenarioUpdate, ScenarioResponse, ScenarioComparisonResponse,
    # Decision Packet
    DecisionPacketCreate, DecisionPacketResponse,
    # AI Commands
    AIExplainTabRequest, AIAskQuestionRequest, AISummarizeRequest, AIResponse,
    # WebSocket
    WSTabChangedMessage, WSTabStateUpdatedMessage, WSAISpeakingMessage,
    # Tab Responses
    ProcessTabResponse, ProcessMilestone, ProcessTask,
    ProgramsTabResponse, LoanProgramSummary,
    ClosingCostsTabResponse, ClosingCostItem,
    # Training
    TrainingSourceCreate, TrainingSourceResponse, PlaybookResponse,
    # Pending Actions
    PendingActionCreate, PendingActionUpdate, PendingActionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice-copresenter", tags=["Voice Co-Presenter"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_connection_manager = None


def set_dependencies(get_db_func):
    """Set dependencies from main.py."""
    global _get_db
    _get_db = get_db_func
    logger.info("Voice Co-Presenter routes dependencies set")


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Voice Co-Presenter routes not initialized")
    yield from _get_db()


async def get_current_user_id(
    token: str = Query(None),
    authorization: str = None,
    db: Session = Depends(get_db),
) -> int:
    """Get user ID from authentication token."""
    import jwt

    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM = "HS256"

    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization[7:]

    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token provided")

    # First try JWT token
    try:
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email:
            result = db.execute(text("""
                SELECT id FROM users WHERE email = :email
            """), {"email": email}).fetchone()
            if result:
                return result[0]
    except jwt.PyJWTError:
        pass

    # Fall back to session token
    result = db.execute(text("""
        SELECT user_id FROM sessions
        WHERE token = :token AND expires_at > NOW()
    """), {"token": auth_token}).fetchone()

    if result:
        return result[0]

    raise HTTPException(status_code=401, detail="Invalid or expired token")


def generate_ulid() -> str:
    """Generate a ULID-like ID."""
    import time
    import random
    import string

    # Timestamp component (first 10 chars)
    timestamp_ms = int(time.time() * 1000)
    timestamp_chars = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
    timestamp_part = ''
    for _ in range(10):
        timestamp_part = timestamp_chars[timestamp_ms % 32] + timestamp_part
        timestamp_ms //= 32

    # Random component (last 16 chars)
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

    return timestamp_part + random_chars


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

class ConnectionManager:
    """Manages WebSocket connections for call sessions."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, call_session_id: str):
        await websocket.accept()
        if call_session_id not in self.active_connections:
            self.active_connections[call_session_id] = []
        self.active_connections[call_session_id].append(websocket)
        logger.info(f"WebSocket connected for call session {call_session_id}")

    def disconnect(self, websocket: WebSocket, call_session_id: str):
        if call_session_id in self.active_connections:
            if websocket in self.active_connections[call_session_id]:
                self.active_connections[call_session_id].remove(websocket)
            if not self.active_connections[call_session_id]:
                del self.active_connections[call_session_id]
        logger.info(f"WebSocket disconnected for call session {call_session_id}")

    async def broadcast(self, call_session_id: str, message: dict):
        if call_session_id in self.active_connections:
            for connection in self.active_connections[call_session_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to WebSocket: {e}")


manager = ConnectionManager()


# =============================================================================
# CALL SESSION ENDPOINTS
# =============================================================================

@router.post("/calls", response_model=CallSessionResponse)
async def create_call_session(
    request: CallSessionCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new call session for video conference with AI co-presenter."""
    try:
        session_id = generate_ulid()

        # Generate Daily.co room or use internal
        channel_id = f"call-{session_id[:8].lower()}"

        # Create room with Daily.co if configured
        daily_api_key = os.getenv("DAILY_API_KEY")
        if daily_api_key and request.provider == VideoProvider.DAILY:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.daily.co/v1/rooms",
                        headers={
                            "Authorization": f"Bearer {daily_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "name": channel_id,
                            "properties": {
                                "enable_recording": "cloud",
                                "enable_chat": True,
                                "enable_screenshare": True,
                                "exp": int((datetime.utcnow().timestamp()) + 86400)  # 24 hours
                            }
                        }
                    ) as resp:
                        if resp.status == 200:
                            room_data = await resp.json()
                            channel_id = room_data.get("name", channel_id)
            except Exception as e:
                logger.warning(f"Failed to create Daily.co room: {e}")

        # Insert call session
        result = db.execute(text("""
            INSERT INTO call_sessions (
                id, client_id, created_by_user_id, started_at, channel_id, provider,
                context_type, active_tab, ai_enabled, ai_mode, participants, state_snapshot,
                status, created_at, updated_at
            ) VALUES (
                :id, :client_id, :user_id, NOW(), :channel_id, :provider,
                :context_type, 'process', false, 'silent', '[]'::jsonb, '{}'::jsonb,
                'active', NOW(), NOW()
            )
            RETURNING id, client_id, created_by_user_id, started_at, ended_at, channel_id,
                      provider, context_type, active_tab, ai_enabled, ai_mode,
                      active_playbook_id, participants, state_snapshot, recording_url,
                      recording_duration, created_at, updated_at
        """), {
            "id": session_id,
            "client_id": request.client_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "provider": request.provider.value,
            "context_type": request.context_type
        })

        row = result.fetchone()
        db.commit()

        return CallSessionResponse(
            id=row.id,
            client_id=row.client_id,
            created_by_user_id=str(row.created_by_user_id),
            started_at=row.started_at,
            ended_at=row.ended_at,
            channel_id=row.channel_id,
            provider=VideoProvider(row.provider),
            context_type=row.context_type,
            active_tab=TabType(row.active_tab),
            ai_enabled=row.ai_enabled,
            ai_mode=AIMode(row.ai_mode),
            active_playbook_id=row.active_playbook_id,
            participants=row.participants or [],
            state_snapshot=row.state_snapshot or {},
            recording_url=row.recording_url,
            recording_duration=row.recording_duration,
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    except Exception as e:
        logger.exception(f"Error creating call session: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calls/{call_session_id}", response_model=CallSessionResponse)
async def get_call_session(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get call session details."""
    result = db.execute(text("""
        SELECT id, client_id, created_by_user_id, started_at, ended_at, channel_id,
               provider, context_type, active_tab, ai_enabled, ai_mode,
               active_playbook_id, participants, state_snapshot, recording_url,
               recording_duration, created_at, updated_at
        FROM call_sessions
        WHERE id = :id
    """), {"id": call_session_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Call session not found")

    return CallSessionResponse(
        id=row.id,
        client_id=row.client_id,
        created_by_user_id=str(row.created_by_user_id),
        started_at=row.started_at,
        ended_at=row.ended_at,
        channel_id=row.channel_id,
        provider=VideoProvider(row.provider),
        context_type=row.context_type,
        active_tab=TabType(row.active_tab),
        ai_enabled=row.ai_enabled,
        ai_mode=AIMode(row.ai_mode),
        active_playbook_id=row.active_playbook_id,
        participants=row.participants or [],
        state_snapshot=row.state_snapshot or {},
        recording_url=row.recording_url,
        recording_duration=row.recording_duration,
        created_at=row.created_at,
        updated_at=row.updated_at
    )


@router.patch("/calls/{call_session_id}", response_model=CallSessionResponse)
async def update_call_session(
    call_session_id: str,
    request: CallSessionUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update call session state."""
    updates = []
    params = {"id": call_session_id}

    if request.active_tab is not None:
        updates.append("active_tab = :active_tab")
        params["active_tab"] = request.active_tab.value
    if request.ai_enabled is not None:
        updates.append("ai_enabled = :ai_enabled")
        params["ai_enabled"] = request.ai_enabled
    if request.ai_mode is not None:
        updates.append("ai_mode = :ai_mode")
        params["ai_mode"] = request.ai_mode.value
    if request.active_playbook_id is not None:
        updates.append("active_playbook_id = :active_playbook_id")
        params["active_playbook_id"] = request.active_playbook_id
    if request.state_snapshot is not None:
        updates.append("state_snapshot = :state_snapshot::jsonb")
        params["state_snapshot"] = json.dumps(request.state_snapshot)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    updates.append("updated_at = NOW()")

    result = db.execute(text(f"""
        UPDATE call_sessions
        SET {', '.join(updates)}
        WHERE id = :id
        RETURNING id, client_id, created_by_user_id, started_at, ended_at, channel_id,
                  provider, context_type, active_tab, ai_enabled, ai_mode,
                  active_playbook_id, participants, state_snapshot, recording_url,
                  recording_duration, created_at, updated_at
    """), params)

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Call session not found")

    # Broadcast update to all participants
    await manager.broadcast(call_session_id, {
        "type": "STATE_UPDATED",
        "active_tab": request.active_tab.value if request.active_tab else None,
        "ai_enabled": request.ai_enabled,
        "ai_mode": request.ai_mode.value if request.ai_mode else None
    })

    return CallSessionResponse(
        id=row.id,
        client_id=row.client_id,
        created_by_user_id=str(row.created_by_user_id),
        started_at=row.started_at,
        ended_at=row.ended_at,
        channel_id=row.channel_id,
        provider=VideoProvider(row.provider),
        context_type=row.context_type,
        active_tab=TabType(row.active_tab),
        ai_enabled=row.ai_enabled,
        ai_mode=AIMode(row.ai_mode),
        active_playbook_id=row.active_playbook_id,
        participants=row.participants or [],
        state_snapshot=row.state_snapshot or {},
        recording_url=row.recording_url,
        recording_duration=row.recording_duration,
        created_at=row.created_at,
        updated_at=row.updated_at
    )


@router.post("/calls/{call_session_id}/end")
async def end_call_session(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """End a call session."""
    result = db.execute(text("""
        UPDATE call_sessions
        SET ended_at = NOW(), status = 'ended', updated_at = NOW()
        WHERE id = :id
        RETURNING id
    """), {"id": call_session_id})

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Call session not found")

    # Broadcast to all participants
    await manager.broadcast(call_session_id, {"type": "CALL_ENDED"})

    return {"status": "success", "message": "Call session ended"}


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@router.websocket("/calls/{call_session_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    call_session_id: str,
):
    """WebSocket endpoint for real-time call state synchronization."""
    await manager.connect(websocket, call_session_id)
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "TAB_CHANGED":
                # Broadcast tab change to all participants
                await manager.broadcast(call_session_id, {
                    "type": "TAB_CHANGED",
                    "active_tab": data.get("active_tab")
                })

            elif message_type == "TAB_STATE_UPDATED":
                # Broadcast tab state update
                await manager.broadcast(call_session_id, {
                    "type": "TAB_STATE_UPDATED",
                    "tab_state": data.get("tab_state")
                })

            elif message_type == "PING":
                await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, call_session_id)


# =============================================================================
# TAB CONTENT ENDPOINTS
# =============================================================================

@router.get("/calls/{call_session_id}/tabs/process", response_model=ProcessTabResponse)
async def get_process_tab(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get process tab data for a call session."""
    # Get the loan/lead associated with this call
    session_result = db.execute(text("""
        SELECT client_id, loan_id, lead_id FROM call_sessions WHERE id = :id
    """), {"id": call_session_id}).fetchone()

    if not session_result:
        raise HTTPException(status_code=404, detail="Call session not found")

    # Get pipeline milestones from the loan
    loan_id = session_result.loan_id
    if loan_id:
        loan_result = db.execute(text("""
            SELECT id, loan_number, status, application_date, submitted_to_uw_at,
                   approval_date, clear_to_close_at, expected_close_date,
                   status_changed_at
            FROM loans
            WHERE id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if loan_result:
            current_status = loan_result.status
            days_in_stage = 0
            if loan_result.status_changed_at:
                days_in_stage = (datetime.utcnow() - loan_result.status_changed_at).days

            milestones = [
                ProcessMilestone(
                    id="1", name="Application",
                    status="complete" if loan_result.application_date else "pending",
                    owner="Borrower"
                ),
                ProcessMilestone(
                    id="2", name="Processing",
                    status="complete" if loan_result.submitted_to_uw_at else ("in_progress" if current_status == "processing" else "pending"),
                    owner="Processor"
                ),
                ProcessMilestone(
                    id="3", name="Underwriting",
                    status="complete" if loan_result.approval_date else ("in_progress" if current_status == "underwriting" else "pending"),
                    owner="Underwriter"
                ),
                ProcessMilestone(
                    id="4", name="Approval",
                    status="complete" if loan_result.clear_to_close_at else ("in_progress" if current_status == "approved" else "pending"),
                    owner="Underwriter"
                ),
                ProcessMilestone(
                    id="5", name="Clear to Close",
                    status="in_progress" if current_status == "clear_to_close" else ("complete" if current_status in ["docs_out", "docs_back", "funded"] else "pending"),
                    owner="Closer"
                ),
                ProcessMilestone(
                    id="6", name="Closing",
                    status="complete" if current_status == "funded" else "pending",
                    owner="Title/Escrow"
                ),
            ]

            return ProcessTabResponse(
                milestones=milestones,
                current_stage=current_status,
                estimated_close_date=loan_result.expected_close_date.isoformat() if loan_result.expected_close_date else None,
                days_in_current_stage=days_in_stage,
                tasks=[]
            )

    # Default response for new leads
    return ProcessTabResponse(
        milestones=[
            ProcessMilestone(id="1", name="Application", status="pending", owner="Borrower"),
            ProcessMilestone(id="2", name="Processing", status="pending", owner="Processor"),
            ProcessMilestone(id="3", name="Underwriting", status="pending", owner="Underwriter"),
            ProcessMilestone(id="4", name="Approval", status="pending", owner="Underwriter"),
            ProcessMilestone(id="5", name="Clear to Close", status="pending", owner="Closer"),
            ProcessMilestone(id="6", name="Closing", status="pending", owner="Title/Escrow"),
        ],
        current_stage="lead",
        estimated_close_date=None,
        days_in_current_stage=0,
        tasks=[]
    )


@router.get("/calls/{call_session_id}/tabs/programs", response_model=ProgramsTabResponse)
async def get_programs_tab(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get available loan programs for the borrower."""
    # Get active rate sheet
    rate_sheet_result = db.execute(text("""
        SELECT id FROM rate_sheets
        WHERE status = 'active'
        ORDER BY effective_at DESC
        LIMIT 1
    """)).fetchone()

    if not rate_sheet_result:
        return ProgramsTabResponse(
            eligible_programs=[],
            recommended_program_id=None,
            client_profile={}
        )

    # Get distinct programs from rate products
    products_result = db.execute(text("""
        SELECT DISTINCT ON (family, program)
            id, family, program, term
        FROM rate_products
        WHERE rate_sheet_id = :rate_sheet_id
        ORDER BY family, program
    """), {"rate_sheet_id": rate_sheet_result.id}).fetchall()

    programs = []
    for p in products_result:
        programs.append(LoanProgramSummary(
            id=p.id,
            family=p.family,
            name=p.program,
            term=p.term,
            min_credit_score=620 if p.family == "AGENCY" else (580 if p.family == "GOV" else 700),
            min_down_payment_pct=3.0 if p.family == "AGENCY" else (3.5 if p.family == "GOV" else 20.0),
            max_dti=50.0 if p.family in ["AGENCY", "GOV"] else 43.0,
            allows_gift_funds=True,
            requires_pmi=p.family == "AGENCY",
            badges=["Popular"] if p.family == "AGENCY" and "30" in p.term else []
        ))

    return ProgramsTabResponse(
        eligible_programs=programs,
        recommended_program_id=programs[0].id if programs else None,
        client_profile={}
    )


# =============================================================================
# RATE SHEET ENDPOINTS
# =============================================================================

@router.post("/rate-sheets", response_model=RateSheetResponse)
async def upload_rate_sheet(
    file: UploadFile = File(...),
    name: str = Query(...),
    branch_code: str = Query(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Upload and parse a rate sheet Excel file."""
    try:
        sheet_id = generate_ulid()
        file_content = await file.read()

        # Save file to S3 or local storage
        file_url = f"/uploads/rate-sheets/{sheet_id}/{file.filename}"

        # Parse Excel file
        import io
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(io.BytesIO(file_content))
            # Basic parsing - would be more sophisticated in production
        except Exception as e:
            logger.warning(f"Failed to parse Excel: {e}")

        # Create rate sheet record
        result = db.execute(text("""
            INSERT INTO rate_sheets (
                id, name, branch_code, effective_at, source, raw_file_url,
                uploaded_by_user_id, status, created_at, updated_at
            ) VALUES (
                :id, :name, :branch_code, NOW(), 'upload', :file_url,
                :user_id, 'pending', NOW(), NOW()
            )
            RETURNING id, name, branch_code, effective_at, expires_at, source,
                      raw_file_url, uploaded_by_user_id, status, price_cap_discount,
                      price_cap_credit, created_at, updated_at
        """), {
            "id": sheet_id,
            "name": name,
            "branch_code": branch_code,
            "file_url": file_url,
            "user_id": user_id
        })

        row = result.fetchone()
        db.commit()

        return RateSheetResponse(
            id=row.id,
            name=row.name,
            branch_code=row.branch_code,
            effective_at=row.effective_at,
            expires_at=row.expires_at,
            source=row.source,
            price_cap_discount=row.price_cap_discount or 4.0,
            price_cap_credit=row.price_cap_credit or -4.0,
            uploaded_by_user_id=str(row.uploaded_by_user_id),
            raw_file_url=row.raw_file_url,
            status=RateSheetStatus(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    except Exception as e:
        logger.exception(f"Error uploading rate sheet: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rate-sheets/active", response_model=RateSheetResponse)
async def get_active_rate_sheet(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get the currently active rate sheet."""
    result = db.execute(text("""
        SELECT id, name, branch_code, effective_at, expires_at, source,
               raw_file_url, uploaded_by_user_id, status, price_cap_discount,
               price_cap_credit, created_at, updated_at
        FROM rate_sheets
        WHERE status = 'active'
        ORDER BY effective_at DESC
        LIMIT 1
    """)).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="No active rate sheet found")

    return RateSheetResponse(
        id=result.id,
        name=result.name,
        branch_code=result.branch_code,
        effective_at=result.effective_at,
        expires_at=result.expires_at,
        source=result.source,
        price_cap_discount=result.price_cap_discount or 4.0,
        price_cap_credit=result.price_cap_credit or -4.0,
        uploaded_by_user_id=str(result.uploaded_by_user_id),
        raw_file_url=result.raw_file_url,
        status=RateSheetStatus(result.status),
        created_at=result.created_at,
        updated_at=result.updated_at
    )


@router.post("/rate-sheets/{rate_sheet_id}/activate")
async def activate_rate_sheet(
    rate_sheet_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Activate a rate sheet (deactivates all others)."""
    # Deactivate all other rate sheets
    db.execute(text("""
        UPDATE rate_sheets SET status = 'superseded', updated_at = NOW()
        WHERE status = 'active'
    """))

    # Activate this rate sheet
    result = db.execute(text("""
        UPDATE rate_sheets
        SET status = 'active', updated_at = NOW()
        WHERE id = :id
        RETURNING id
    """), {"id": rate_sheet_id})

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Rate sheet not found")

    return {"status": "success", "message": "Rate sheet activated"}


@router.get("/rate-sheets/{rate_sheet_id}/rates")
async def get_rate_ladder(
    rate_sheet_id: str,
    product_family: str = Query("AGENCY"),
    program: str = Query("30 Year Fixed"),
    lock_days: int = Query(30),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get rate ladder for a specific product/program/lock combination."""
    # Get product
    product_result = db.execute(text("""
        SELECT id, family, program, term
        FROM rate_products
        WHERE rate_sheet_id = :rate_sheet_id
          AND family = :family
          AND program = :program
        LIMIT 1
    """), {
        "rate_sheet_id": rate_sheet_id,
        "family": product_family,
        "program": program
    }).fetchone()

    if not product_result:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get rate lock
    lock_result = db.execute(text("""
        SELECT id FROM rate_locks
        WHERE rate_product_id = :product_id AND lock_days = :lock_days
        LIMIT 1
    """), {
        "product_id": product_result.id,
        "lock_days": lock_days
    }).fetchone()

    if not lock_result:
        # Return empty rates if no lock period found
        return {
            "rate_sheet_id": rate_sheet_id,
            "product_family": product_family,
            "program": program,
            "lock_days": lock_days,
            "rates": []
        }

    # Get rates
    rates_result = db.execute(text("""
        SELECT id, rate, price, is_par
        FROM rate_rows
        WHERE rate_lock_id = :lock_id
        ORDER BY rate ASC
    """), {"lock_id": lock_result.id}).fetchall()

    return {
        "rate_sheet_id": rate_sheet_id,
        "product_family": product_family,
        "program": program,
        "lock_days": lock_days,
        "rates": [
            {
                "id": r.id,
                "rate": r.rate,
                "price": r.price,
                "is_par": r.is_par
            }
            for r in rates_result
        ]
    }


# =============================================================================
# SCENARIO ENDPOINTS
# =============================================================================

@router.post("/scenarios", response_model=ScenarioResponse)
async def create_scenario(
    request: ScenarioCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new loan scenario for comparison."""
    try:
        scenario_id = generate_ulid()

        # Get rate details
        rate_result = db.execute(text("""
            SELECT rr.rate, rr.price
            FROM rate_rows rr
            WHERE rr.id = :rate_row_id
        """), {"rate_row_id": request.rate_row_id}).fetchone()

        if not rate_result:
            raise HTTPException(status_code=404, detail="Rate row not found")

        # Calculate scenario values
        rate = rate_result.rate
        price = rate_result.price
        loan_amount = request.loan_amount
        points_dollars = loan_amount * (price / 100)

        # Calculate P&I payment (30-year fixed assumption)
        monthly_rate = rate / 100 / 12
        term_months = 360
        if monthly_rate > 0:
            payment_pi = loan_amount * (
                monthly_rate * (1 + monthly_rate) ** term_months
            ) / (
                (1 + monthly_rate) ** term_months - 1
            )
        else:
            payment_pi = loan_amount / term_months

        # Estimate PITI (P&I + taxes + insurance)
        monthly_taxes = loan_amount * 0.0125 / 12  # 1.25% annual tax rate
        monthly_insurance = loan_amount * 0.003 / 12  # 0.3% annual
        payment_piti = payment_pi + monthly_taxes + monthly_insurance

        # Estimate cash to close
        down_payment = loan_amount * 0.2  # Assume 20% down
        closing_costs = 8000  # Fixed estimate
        cash_to_close = down_payment + closing_costs + max(0, points_dollars)

        # Insert scenario
        result = db.execute(text("""
            INSERT INTO scenarios (
                id, client_id, call_session_id, name, program_id, rate_row_id,
                loan_amount, rate, price, points_dollars, payment_pi, payment_piti,
                cash_to_close, is_recommended, created_at, updated_at
            ) VALUES (
                :id, :client_id, :call_session_id, :name, :program_id, :rate_row_id,
                :loan_amount, :rate, :price, :points_dollars, :payment_pi, :payment_piti,
                :cash_to_close, false, NOW(), NOW()
            )
            RETURNING *
        """), {
            "id": scenario_id,
            "client_id": request.client_id,
            "call_session_id": request.call_session_id,
            "name": request.name,
            "program_id": request.program_id,
            "rate_row_id": request.rate_row_id,
            "loan_amount": loan_amount,
            "rate": rate,
            "price": price,
            "points_dollars": points_dollars,
            "payment_pi": round(payment_pi, 2),
            "payment_piti": round(payment_piti, 2),
            "cash_to_close": round(cash_to_close, 2)
        })

        row = result.fetchone()
        db.commit()

        return ScenarioResponse(
            id=row.id,
            decision_packet_id=row.decision_packet_id,
            client_id=row.client_id,
            call_session_id=row.call_session_id,
            name=row.name,
            program_id=row.program_id,
            rate_row_id=row.rate_row_id,
            loan_amount=row.loan_amount,
            rate=row.rate,
            price=row.price,
            points_dollars=row.points_dollars,
            payment_pi=row.payment_pi,
            payment_piti=row.payment_piti,
            cash_to_close=row.cash_to_close,
            breakeven_months=row.breakeven_months,
            total_cost_year_1=row.total_cost_year_1,
            total_cost_year_5=row.total_cost_year_5,
            is_recommended=row.is_recommended,
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    except Exception as e:
        logger.exception(f"Error creating scenario: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/compare", response_model=ScenarioComparisonResponse)
async def compare_scenarios(
    client_id: str = Query(None),
    call_session_id: str = Query(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get all scenarios for comparison."""
    filters = []
    params = {}

    if client_id:
        filters.append("client_id = :client_id")
        params["client_id"] = client_id
    if call_session_id:
        filters.append("call_session_id = :call_session_id")
        params["call_session_id"] = call_session_id

    if not filters:
        raise HTTPException(status_code=400, detail="client_id or call_session_id required")

    where_clause = " AND ".join(filters)

    result = db.execute(text(f"""
        SELECT * FROM scenarios
        WHERE {where_clause}
        ORDER BY created_at DESC
    """), params).fetchall()

    scenarios = [
        ScenarioResponse(
            id=row.id,
            decision_packet_id=row.decision_packet_id,
            client_id=row.client_id,
            call_session_id=row.call_session_id,
            name=row.name,
            program_id=row.program_id,
            rate_row_id=row.rate_row_id,
            loan_amount=row.loan_amount,
            rate=row.rate,
            price=row.price,
            points_dollars=row.points_dollars,
            payment_pi=row.payment_pi,
            payment_piti=row.payment_piti,
            cash_to_close=row.cash_to_close,
            breakeven_months=row.breakeven_months,
            total_cost_year_1=row.total_cost_year_1,
            total_cost_year_5=row.total_cost_year_5,
            is_recommended=row.is_recommended,
            created_at=row.created_at,
            updated_at=row.updated_at
        )
        for row in result
    ]

    return ScenarioComparisonResponse(
        scenarios=scenarios,
        client_id=client_id,
        call_session_id=call_session_id
    )


@router.post("/scenarios/{scenario_id}/recommend")
async def set_scenario_recommended(
    scenario_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Mark a scenario as recommended."""
    # Get the scenario's client_id
    scenario_result = db.execute(text("""
        SELECT client_id FROM scenarios WHERE id = :id
    """), {"id": scenario_id}).fetchone()

    if not scenario_result:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Unmark all other scenarios for this client
    db.execute(text("""
        UPDATE scenarios SET is_recommended = false
        WHERE client_id = :client_id
    """), {"client_id": scenario_result.client_id})

    # Mark this scenario as recommended
    db.execute(text("""
        UPDATE scenarios SET is_recommended = true, updated_at = NOW()
        WHERE id = :id
    """), {"id": scenario_id})

    db.commit()

    return {"status": "success", "message": "Scenario marked as recommended"}


# =============================================================================
# AI VOICE COMMANDS
# =============================================================================

@router.post("/calls/{call_session_id}/ai/explain-tab", response_model=AIResponse)
async def ai_explain_tab(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Trigger AI to explain the current tab."""
    # Get session state
    session_result = db.execute(text("""
        SELECT active_tab, ai_enabled, active_playbook_id
        FROM call_sessions
        WHERE id = :id
    """), {"id": call_session_id}).fetchone()

    if not session_result:
        raise HTTPException(status_code=404, detail="Call session not found")

    if not session_result.ai_enabled:
        raise HTTPException(status_code=400, detail="AI is not enabled for this call")

    active_tab = session_result.active_tab

    # Get tab script if playbook is set
    explain_text = ""
    if session_result.active_playbook_id:
        script_result = db.execute(text("""
            SELECT explain_template
            FROM tab_scripts
            WHERE playbook_id = :playbook_id AND tab = :tab
        """), {
            "playbook_id": session_result.active_playbook_id,
            "tab": active_tab.upper()
        }).fetchone()

        if script_result:
            explain_text = script_result.explain_template

    # Default explanations if no playbook
    if not explain_text:
        tab_explanations = {
            "process": "Here's where we are in your loan process. I'll walk you through each milestone and what needs to happen next.",
            "programs": "These are the loan programs you qualify for based on your profile. Each has different requirements and benefits.",
            "rates": "Rates have tradeoffs. A lower rate usually costs points upfront. A higher rate can create a lender credit to reduce your closing costs.",
            "comparison": "Let's compare these scenarios side by side. I'll help you understand the differences in payment, cash needed, and total cost.",
            "closing_costs": "Here are all the costs involved in closing your loan. I'll show you how lender credits can reduce what you pay out of pocket."
        }
        explain_text = tab_explanations.get(active_tab, "Let me explain what you're looking at.")

    # Log AI event
    event_id = generate_ulid()
    db.execute(text("""
        INSERT INTO ai_event_logs (
            id, call_session_id, event_type, timestamp, speaker,
            ai_utterance, created_at
        ) VALUES (
            :id, :call_session_id, 'AI_UTTERANCE', NOW(), 'ai',
            :utterance, NOW()
        )
    """), {
        "id": event_id,
        "call_session_id": call_session_id,
        "utterance": explain_text
    })
    db.commit()

    # Broadcast AI speaking to all participants
    await manager.broadcast(call_session_id, {
        "type": "AI_SPEAKING",
        "text": explain_text
    })

    return AIResponse(
        status="speaking",
        text=explain_text
    )


@router.post("/calls/{call_session_id}/ai/summarize", response_model=AIResponse)
async def ai_summarize(
    call_session_id: str,
    include_recommendations: bool = Query(True),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Trigger AI to summarize the discussion."""
    # Get session and scenarios
    session_result = db.execute(text("""
        SELECT client_id, ai_enabled FROM call_sessions WHERE id = :id
    """), {"id": call_session_id}).fetchone()

    if not session_result:
        raise HTTPException(status_code=404, detail="Call session not found")

    if not session_result.ai_enabled:
        raise HTTPException(status_code=400, detail="AI is not enabled for this call")

    # Get scenarios for summary
    scenarios_result = db.execute(text("""
        SELECT name, rate, price, payment_pi, cash_to_close, is_recommended
        FROM scenarios
        WHERE client_id = :client_id
        ORDER BY created_at DESC
    """), {"client_id": session_result.client_id}).fetchall()

    summary_parts = ["Here's a summary of what we discussed today:"]

    if scenarios_result:
        summary_parts.append(f"We looked at {len(scenarios_result)} different scenarios.")

        recommended = next((s for s in scenarios_result if s.is_recommended), None)
        if recommended and include_recommendations:
            summary_parts.append(
                f"The recommended option is {recommended.name} with a {recommended.rate}% rate, "
                f"monthly payment of ${recommended.payment_pi:,.0f}, "
                f"and ${recommended.cash_to_close:,.0f} needed at closing."
            )
    else:
        summary_parts.append("We discussed your loan options and timeline.")

    summary_parts.append("Your loan officer will follow up with next steps and any additional information you need.")

    summary_text = " ".join(summary_parts)

    # Log AI event
    event_id = generate_ulid()
    db.execute(text("""
        INSERT INTO ai_event_logs (
            id, call_session_id, event_type, timestamp, speaker,
            ai_utterance, created_at
        ) VALUES (
            :id, :call_session_id, 'AI_UTTERANCE', NOW(), 'ai',
            :utterance, NOW()
        )
    """), {
        "id": event_id,
        "call_session_id": call_session_id,
        "utterance": summary_text
    })
    db.commit()

    await manager.broadcast(call_session_id, {
        "type": "AI_SPEAKING",
        "text": summary_text
    })

    return AIResponse(
        status="speaking",
        text=summary_text
    )


@router.post("/calls/{call_session_id}/ai/mute")
async def ai_mute(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Immediately mute the AI presenter."""
    await manager.broadcast(call_session_id, {"type": "AI_STOPPED"})

    return {"status": "success", "message": "AI muted"}


# =============================================================================
# PENDING ACTIONS
# =============================================================================

@router.get("/calls/{call_session_id}/pending-actions", response_model=List[PendingActionResponse])
async def get_pending_actions(
    call_session_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get pending actions awaiting approval."""
    result = db.execute(text("""
        SELECT id, call_session_id, action_type, proposed_by, proposed_at,
               status, reviewed_by_user_id, reviewed_at, payload, created_at
        FROM pending_actions
        WHERE call_session_id = :call_session_id AND status = 'PENDING'
        ORDER BY proposed_at DESC
    """), {"call_session_id": call_session_id}).fetchall()

    return [
        PendingActionResponse(
            id=row.id,
            call_session_id=row.call_session_id,
            action_type=row.action_type,
            proposed_by=row.proposed_by,
            proposed_at=row.proposed_at,
            status=row.status,
            reviewed_by_user_id=str(row.reviewed_by_user_id) if row.reviewed_by_user_id else None,
            reviewed_at=row.reviewed_at,
            payload=row.payload,
            created_at=row.created_at
        )
        for row in result
    ]


@router.post("/pending-actions/{action_id}/approve")
async def approve_pending_action(
    action_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Approve a pending action."""
    result = db.execute(text("""
        UPDATE pending_actions
        SET status = 'APPROVED', reviewed_by_user_id = :user_id, reviewed_at = NOW()
        WHERE id = :id AND status = 'PENDING'
        RETURNING id, call_session_id, action_type, payload
    """), {"id": action_id, "user_id": user_id})

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Pending action not found or already processed")

    # Execute the action based on type
    # TODO: Implement action execution logic

    await manager.broadcast(row.call_session_id, {
        "type": "ACTION_APPROVED",
        "action_id": action_id
    })

    return {"status": "success", "message": "Action approved"}


@router.post("/pending-actions/{action_id}/reject")
async def reject_pending_action(
    action_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Reject a pending action."""
    result = db.execute(text("""
        UPDATE pending_actions
        SET status = 'REJECTED', reviewed_by_user_id = :user_id, reviewed_at = NOW()
        WHERE id = :id AND status = 'PENDING'
        RETURNING id, call_session_id
    """), {"id": action_id, "user_id": user_id})

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Pending action not found or already processed")

    await manager.broadcast(row.call_session_id, {
        "type": "ACTION_REJECTED",
        "action_id": action_id
    })

    return {"status": "success", "message": "Action rejected"}


# =============================================================================
# DECISION PACKET
# =============================================================================

@router.post("/calls/{call_session_id}/publish", response_model=DecisionPacketResponse)
async def publish_decision_packet(
    call_session_id: str,
    request: DecisionPacketCreate = Body(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Publish a decision packet to the borrower portal."""
    try:
        packet_id = generate_ulid()

        # Get session details
        session_result = db.execute(text("""
            SELECT client_id FROM call_sessions WHERE id = :id
        """), {"id": call_session_id}).fetchone()

        if not session_result:
            raise HTTPException(status_code=404, detail="Call session not found")

        # Get rate sheet effective date
        rate_sheet_result = db.execute(text("""
            SELECT effective_at FROM rate_sheets WHERE id = :id
        """), {"id": request.rate_sheet_id}).fetchone()

        if not rate_sheet_result:
            raise HTTPException(status_code=404, detail="Rate sheet not found")

        # Get scenarios
        scenarios_result = db.execute(text("""
            SELECT * FROM scenarios
            WHERE client_id = :client_id
        """), {"client_id": session_result.client_id}).fetchall()

        scenarios_json = [
            {
                "id": s.id,
                "name": s.name,
                "rate": s.rate,
                "price": s.price,
                "payment_pi": s.payment_pi,
                "payment_piti": s.payment_piti,
                "cash_to_close": s.cash_to_close,
                "is_recommended": s.is_recommended
            }
            for s in scenarios_result
        ]

        # Determine version
        version_result = db.execute(text("""
            SELECT COALESCE(MAX(version), 0) + 1 as next_version
            FROM decision_packets
            WHERE client_id = :client_id
        """), {"client_id": session_result.client_id}).fetchone()

        version = version_result.next_version

        # Create decision packet
        result = db.execute(text("""
            INSERT INTO decision_packets (
                id, call_session_id, client_id, created_by_user_id, published_at,
                rate_sheet_id, effective_at, approved_tabs, scenarios, assumptions,
                disclosures, disclaimer_text, version, created_at
            ) VALUES (
                :id, :call_session_id, :client_id, :user_id, NOW(),
                :rate_sheet_id, :effective_at, :approved_tabs, :scenarios::jsonb, :assumptions::jsonb,
                :disclosures::jsonb, :disclaimer_text, :version, NOW()
            )
            RETURNING *
        """), {
            "id": packet_id,
            "call_session_id": call_session_id,
            "client_id": request.client_id,
            "user_id": user_id,
            "rate_sheet_id": request.rate_sheet_id,
            "effective_at": rate_sheet_result.effective_at,
            "approved_tabs": json.dumps([t.value for t in request.approved_tabs]),
            "scenarios": json.dumps(scenarios_json),
            "assumptions": json.dumps({}),
            "disclosures": json.dumps({}),
            "disclaimer_text": request.disclaimer_text,
            "version": version
        })

        row = result.fetchone()
        db.commit()

        # Log AI event
        event_id = generate_ulid()
        db.execute(text("""
            INSERT INTO ai_event_logs (
                id, call_session_id, event_type, timestamp, created_at
            ) VALUES (
                :id, :call_session_id, 'PACKET_PUBLISHED', NOW(), NOW()
            )
        """), {
            "id": event_id,
            "call_session_id": call_session_id
        })
        db.commit()

        return DecisionPacketResponse(
            id=row.id,
            call_session_id=row.call_session_id,
            client_id=row.client_id,
            created_by_user_id=str(row.created_by_user_id),
            published_at=row.published_at,
            rate_sheet_id=row.rate_sheet_id,
            effective_at=row.effective_at,
            approved_tabs=[TabType(t) for t in row.approved_tabs],
            scenarios=row.scenarios,
            assumptions=row.assumptions,
            disclosures=row.disclosures,
            disclaimer_text=row.disclaimer_text,
            pdf_url=row.pdf_url,
            version=row.version,
            supersedes=row.supersedes,
            created_at=row.created_at
        )

    except Exception as e:
        logger.exception(f"Error publishing decision packet: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TRAINING SYSTEM
# =============================================================================

@router.post("/training/sources", response_model=TrainingSourceResponse)
async def create_training_source(
    request: TrainingSourceCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new training source (YouTube, PDF, etc.)."""
    try:
        source_id = generate_ulid()

        result = db.execute(text("""
            INSERT INTO training_sources (
                id, type, title, url, status, created_by_user_id, created_at, updated_at
            ) VALUES (
                :id, :type, :title, :url, 'PENDING', :user_id, NOW(), NOW()
            )
            RETURNING *
        """), {
            "id": source_id,
            "type": request.type.value,
            "title": request.title,
            "url": request.url,
            "user_id": user_id
        })

        row = result.fetchone()
        db.commit()

        # TODO: Trigger async ingestion job

        return TrainingSourceResponse(
            id=row.id,
            type=row.type,
            title=row.title,
            url=row.url,
            status=row.status,
            error=row.error,
            total_chunks=row.total_chunks,
            processed_chunks=row.processed_chunks,
            created_by_user_id=str(row.created_by_user_id),
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    except Exception as e:
        logger.exception(f"Error creating training source: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/sources", response_model=List[TrainingSourceResponse])
async def list_training_sources(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """List all training sources."""
    result = db.execute(text("""
        SELECT * FROM training_sources
        ORDER BY created_at DESC
    """)).fetchall()

    return [
        TrainingSourceResponse(
            id=row.id,
            type=row.type,
            title=row.title,
            url=row.url,
            status=row.status,
            error=row.error,
            total_chunks=row.total_chunks,
            processed_chunks=row.processed_chunks,
            created_by_user_id=str(row.created_by_user_id),
            created_at=row.created_at,
            updated_at=row.updated_at
        )
        for row in result
    ]


@router.get("/training/playbooks", response_model=List[PlaybookResponse])
async def list_playbooks(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """List all playbooks."""
    result = db.execute(text("""
        SELECT * FROM playbooks
        ORDER BY created_at DESC
    """)).fetchall()

    return [
        PlaybookResponse(
            id=row.id,
            training_source_id=row.training_source_id,
            name=row.name,
            version=row.version,
            active=row.active,
            created_by_user_id=str(row.created_by_user_id),
            created_at=row.created_at,
            updated_at=row.updated_at
        )
        for row in result
    ]


@router.post("/training/playbooks/{playbook_id}/activate")
async def activate_playbook(
    playbook_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Activate a playbook (deactivates all others)."""
    # Deactivate all playbooks
    db.execute(text("""
        UPDATE playbooks SET active = false, updated_at = NOW()
    """))

    # Activate this playbook
    result = db.execute(text("""
        UPDATE playbooks
        SET active = true, updated_at = NOW()
        WHERE id = :id
        RETURNING id
    """), {"id": playbook_id})

    row = result.fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Playbook not found")

    return {"status": "success", "message": "Playbook activated"}
