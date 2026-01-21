"""
Call Monitoring Routes

API endpoints for the AI call monitoring system:
- Session management (create, update, end)
- Transcript handling (stream chunks, get full transcript)
- Agent processing and artifacts
- Review and approval workflow
- Artifact execution
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, BackgroundTasks,
    Query, Request, status
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.call_monitoring_models import (
    CaptureMode, CallSessionStatus as SessionStatus,
    ArtifactType, ApprovalStatus,
    CallSessionCreate, CallSessionResponse,
    CallParticipantCreate, CallParticipantResponse,
    CallArtifactResponse, AgentRunResponse,
)
from services.call_monitoring import CallMonitoringOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/call-monitoring", tags=["Call Monitoring"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_current_user = None


def set_dependencies(user_dependency, oauth2=None):
    """Set the get_current_user dependency from main app."""
    global _get_current_user
    _get_current_user = user_dependency


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user dependency wrapper."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _get_current_user is None:
        # Development fallback - return mock user
        return {"id": 1, "email": "admin@perenniaai.com", "role": "admin"}

    try:
        return await _get_current_user(token=token, request=request, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(db: Session) -> int:
    """Get current user ID - simplified fallback."""
    result = db.execute(text("SELECT id FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1")).fetchone()
    return result[0] if result else 1


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new call session."""
    capture_mode: str = Field(..., description="mobile_app, crm_web_call, ambient_mic, or video_call")
    recording_id: Optional[str] = None
    loan_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    participants: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateSessionRequest(BaseModel):
    """Request to update a call session."""
    status: Optional[str] = None
    participants: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class EndSessionRequest(BaseModel):
    """Request to end a call session and trigger processing."""
    final_transcript: Optional[str] = None
    run_agents: bool = True
    agent_types: Optional[List[str]] = None  # If None, run all agents


class TranscriptChunkRequest(BaseModel):
    """Request to add a transcript chunk."""
    text: str
    speaker_label: Optional[str] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    confidence: Optional[float] = None
    is_final: bool = False


class ApproveArtifactsRequest(BaseModel):
    """Request to approve artifacts."""
    artifact_ids: List[str]
    approval_notes: Optional[str] = None


class RejectArtifactsRequest(BaseModel):
    """Request to reject artifacts."""
    artifact_ids: List[str]
    rejection_reason: Optional[str] = None


class ExecuteArtifactsRequest(BaseModel):
    """Request to execute approved artifacts."""
    artifact_ids: Optional[List[str]] = None  # If None, execute all approved


class RunAgentsRequest(BaseModel):
    """Request to manually run agents."""
    agent_types: Optional[List[str]] = None  # If None, run all
    force_rerun: bool = False


class AddParticipantRequest(BaseModel):
    """Request to add a participant to a session."""
    role: str = Field(..., description="loan_officer, borrower, co_borrower, realtor, other")
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    speaker_label: Optional[str] = None
    contact_id: Optional[str] = None
    user_id: Optional[str] = None


class SessionListResponse(BaseModel):
    """Response for list of sessions."""
    sessions: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class ReviewDataResponse(BaseModel):
    """Response containing all data for the review screen."""
    session: Dict[str, Any]
    participants: List[Dict[str, Any]]
    transcript: Optional[str]
    artifacts: List[Dict[str, Any]]
    agent_runs: List[Dict[str, Any]]
    summary: Optional[Dict[str, Any]]


# =============================================================================
# SESSION MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/sessions", response_model=Dict[str, Any])
async def create_session(
    request: CreateSessionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new call monitoring session.

    Starts tracking a call for AI processing. Can be linked to a loan, lead, or contact.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        # Validate capture mode
        try:
            capture_mode = CaptureMode(request.capture_mode)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid capture_mode. Must be one of: {[m.value for m in CaptureMode]}"
            )

        result = orchestrator.create_session(
            capture_mode=capture_mode.value,
            recording_id=request.recording_id,
            loan_id=request.loan_id,
            lead_id=request.lead_id,
            contact_id=request.contact_id,
            participants=request.participants,
            metadata=request.metadata,
            user_id=str(current_user.get("id")),
        )

        return {
            "status": "success",
            "session_id": result["session_id"],
            "capture_mode": capture_mode.value,
            "created_at": result["started_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=Dict[str, Any])
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get call session details."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sessions/{session_id}", response_model=Dict[str, Any])
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update call session details."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update using orchestrator method
        orchestrator.update_session(
            session_id=session_id,
            status=request.status,
            metadata=request.metadata,
        )

        return {
            "status": "success",
            "session_id": session_id,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/end", response_model=Dict[str, Any])
async def end_session(
    session_id: str,
    request: EndSessionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    End a call session and optionally trigger AI processing.

    This marks the session as completed and, if run_agents=True, queues
    the agents to process the transcript.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update session status and set transcript if provided
        now = datetime.utcnow()
        orchestrator.update_session(session_id, status='processing', ended_at=now)

        if request.final_transcript:
            orchestrator.set_transcript(session_id, request.final_transcript)

        response = {
            "status": "success",
            "session_id": session_id,
            "ended_at": now.isoformat(),
        }

        if request.run_agents:
            # Run agents in background
            background_tasks.add_task(
                run_agents_background,
                db_url=str(db.get_bind().url),
                session_id=session_id,
                agent_types=request.agent_types,
                user_id=current_user.get("id"),
            )
            response["agents_queued"] = True

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    loan_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    status: Optional[str] = None,
    capture_mode: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List call sessions with optional filters."""
    try:
        # Build query
        query = "SELECT * FROM call_sessions WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM call_sessions WHERE 1=1"
        params = {}

        if loan_id:
            query += " AND loan_id = :loan_id"
            count_query += " AND loan_id = :loan_id"
            params["loan_id"] = loan_id

        if lead_id:
            query += " AND lead_id = :lead_id"
            count_query += " AND lead_id = :lead_id"
            params["lead_id"] = lead_id

        if contact_id:
            query += " AND contact_id = :contact_id"
            count_query += " AND contact_id = :contact_id"
            params["contact_id"] = contact_id

        if status:
            query += " AND status = :status"
            count_query += " AND status = :status"
            params["status"] = status

        if capture_mode:
            query += " AND capture_mode = :capture_mode"
            count_query += " AND capture_mode = :capture_mode"
            params["capture_mode"] = capture_mode

        # Get total count
        total = db.execute(text(count_query), params).scalar()

        # Get paginated results
        offset = (page - 1) * page_size
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = page_size
        params["offset"] = offset

        result = db.execute(text(query), params)
        sessions = [dict(row._mapping) for row in result]

        # Convert UUIDs to strings
        for session in sessions:
            for key in session:
                if isinstance(session[key], UUID):
                    session[key] = str(session[key])
                elif isinstance(session[key], datetime):
                    session[key] = session[key].isoformat()

        return SessionListResponse(
            sessions=sessions,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TRANSCRIPT ENDPOINTS
# =============================================================================

@router.post("/sessions/{session_id}/transcript/chunk", response_model=Dict[str, Any])
async def add_transcript_chunk(
    session_id: str,
    request: TranscriptChunkRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Add a transcript chunk to a session.

    Used for streaming transcripts from real-time transcription services.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        # Format chunk with speaker if provided
        chunk_text = request.text
        if request.speaker_label:
            chunk_text = f"[{request.speaker_label}]: {request.text}"

        await orchestrator.process_transcript_chunk(
            session_id=session_id,
            chunk=chunk_text,
            speaker=request.speaker_label,
            timestamp_ms=request.start_time_ms,
        )

        return {
            "status": "success",
            "session_id": session_id,
            "chunk_received": True,
        }

    except Exception as e:
        logger.error(f"Error adding transcript chunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/transcript", response_model=Dict[str, Any])
async def get_transcript(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the full transcript for a session."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        transcript_data = orchestrator.get_transcript(session_id)

        if not transcript_data:
            raise HTTPException(status_code=404, detail="Session not found")

        session = orchestrator.get_session(session_id)

        return {
            "session_id": session_id,
            "transcript_state": transcript_data.get("state"),
            "full_transcript": transcript_data.get("transcript"),
            "word_count": transcript_data.get("word_count"),
            "participants": session.get("participants", []) if session else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AGENT & ARTIFACT ENDPOINTS
# =============================================================================

@router.post("/sessions/{session_id}/run-agents", response_model=Dict[str, Any])
async def run_agents(
    session_id: str,
    request: RunAgentsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger agent processing for a session.

    By default runs all three agents (scribe, junior_lo, underwriter).
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if not session.get("full_transcript"):
            raise HTTPException(
                status_code=400,
                detail="No transcript available. Add transcript before running agents."
            )

        # Run agents in background
        background_tasks.add_task(
            run_agents_background,
            db_url=str(db.get_bind().url),
            session_id=session_id,
            agent_types=request.agent_types,
            user_id=current_user.get("id"),
            force_rerun=request.force_rerun,
        )

        return {
            "status": "success",
            "session_id": session_id,
            "agents_queued": request.agent_types or ["scribe", "junior_lo", "underwriter"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/artifacts", response_model=Dict[str, Any])
async def get_artifacts(
    session_id: str,
    artifact_type: Optional[str] = None,
    approval_status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get artifacts for a session with optional filters."""
    try:
        query = "SELECT * FROM call_artifacts WHERE session_id = :session_id"
        params = {"session_id": session_id}

        if artifact_type:
            query += " AND artifact_type = :artifact_type"
            params["artifact_type"] = artifact_type

        if approval_status:
            query += " AND approval_status = :approval_status"
            params["approval_status"] = approval_status

        query += " ORDER BY created_at DESC"

        result = db.execute(text(query), params)
        artifacts = [dict(row._mapping) for row in result]

        # Convert types
        for artifact in artifacts:
            for key in artifact:
                if isinstance(artifact[key], UUID):
                    artifact[key] = str(artifact[key])
                elif isinstance(artifact[key], datetime):
                    artifact[key] = artifact[key].isoformat()

        # Group by type
        by_type = {}
        for artifact in artifacts:
            atype = artifact.get("artifact_type", "other")
            if atype not in by_type:
                by_type[atype] = []
            by_type[atype].append(artifact)

        return {
            "session_id": session_id,
            "total": len(artifacts),
            "artifacts": artifacts,
            "by_type": by_type,
        }

    except Exception as e:
        logger.error(f"Error getting artifacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/artifacts/approve", response_model=Dict[str, Any])
async def approve_artifacts(
    session_id: str,
    request: ApproveArtifactsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Approve selected artifacts."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        result = await orchestrator.approve_artifacts(
            session_id=session_id,
            artifact_ids=request.artifact_ids,
            user_id=str(current_user.get("id")),
            action='approve',
        )

        return {
            "status": "success",
            "session_id": session_id,
            "approved_count": result.get("count", 0),
        }

    except Exception as e:
        logger.error(f"Error approving artifacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/artifacts/reject", response_model=Dict[str, Any])
async def reject_artifacts(
    session_id: str,
    request: RejectArtifactsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Reject selected artifacts."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        rejected = await orchestrator.reject_artifacts(
            session_id=session_id,
            artifact_ids=request.artifact_ids,
            user_id=str(current_user.get("id")),
            rejection_reason=request.rejection_reason,
        )

        return {
            "status": "success",
            "session_id": session_id,
            "rejected_count": rejected,
        }

    except Exception as e:
        logger.error(f"Error rejecting artifacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/artifacts/execute", response_model=Dict[str, Any])
async def execute_artifacts(
    session_id: str,
    request: ExecuteArtifactsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Execute approved artifacts.

    This creates tasks, document requests, conditions, etc. from approved artifacts.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        results = await orchestrator.execute_approved_artifacts(
            session_id=session_id,
            user_id=str(current_user.get("id")),
        )

        executed_count = len(results.get("executed", []))

        return {
            "status": "success",
            "session_id": session_id,
            "executed_count": executed_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error executing artifacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REVIEW SCREEN ENDPOINTS
# =============================================================================

@router.get("/sessions/{session_id}/review", response_model=Dict[str, Any])
async def get_review_data(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all data needed for the review screen.

    Returns session info, transcript, all artifacts, and agent run details.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        review_data = orchestrator.get_review_data(session_id)

        if not review_data:
            raise HTTPException(status_code=404, detail="Session not found")

        return review_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting review data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/review/submit", response_model=Dict[str, Any])
async def submit_review(
    session_id: str,
    request: ApproveArtifactsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Submit the review with approved artifacts.

    This approves selected artifacts and triggers execution.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        user_id = str(current_user.get("id"))

        # Approve artifacts
        approval_result = await orchestrator.approve_artifacts(
            session_id=session_id,
            artifact_ids=request.artifact_ids,
            user_id=user_id,
            action='approve',
        )

        # Execute approved artifacts
        results = await orchestrator.execute_approved_artifacts(
            session_id=session_id,
            user_id=user_id,
        )

        # Update session status
        orchestrator.update_session(session_id, status='completed')

        executed_count = len(results.get("executed", []))

        return {
            "status": "success",
            "session_id": session_id,
            "approved_count": approval_result.get("count", 0),
            "executed_count": executed_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error submitting review: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PARTICIPANT ENDPOINTS
# =============================================================================

@router.post("/sessions/{session_id}/participants", response_model=Dict[str, Any])
async def add_participant(
    session_id: str,
    request: AddParticipantRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Add a participant to a call session."""
    try:
        orchestrator = CallMonitoringOrchestrator(db)

        participant = await orchestrator.add_participant(
            session_id=session_id,
            role=request.role,
            name=request.name,
            phone=request.phone,
            email=request.email,
            speaker_label=request.speaker_label,
            contact_id=request.contact_id,
            user_id=request.user_id,
        )

        return {
            "status": "success",
            "participant_id": str(participant.id),
            "session_id": session_id,
        }

    except Exception as e:
        logger.error(f"Error adding participant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/participants", response_model=Dict[str, Any])
async def get_participants(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all participants for a session."""
    try:
        result = db.execute(
            text("SELECT * FROM call_participants WHERE session_id = :session_id ORDER BY joined_at"),
            {"session_id": session_id}
        )
        participants = [dict(row._mapping) for row in result]

        # Convert types
        for p in participants:
            for key in p:
                if isinstance(p[key], UUID):
                    p[key] = str(p[key])
                elif isinstance(p[key], datetime):
                    p[key] = p[key].isoformat()

        return {
            "session_id": session_id,
            "participants": participants,
        }

    except Exception as e:
        logger.error(f"Error getting participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AGENT RUN ENDPOINTS
# =============================================================================

@router.get("/sessions/{session_id}/agent-runs", response_model=Dict[str, Any])
async def get_agent_runs(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all agent runs for a session."""
    try:
        result = db.execute(
            text("SELECT * FROM agent_runs WHERE session_id = :session_id ORDER BY started_at DESC"),
            {"session_id": session_id}
        )
        runs = [dict(row._mapping) for row in result]

        # Convert types
        for run in runs:
            for key in run:
                if isinstance(run[key], UUID):
                    run[key] = str(run[key])
                elif isinstance(run[key], datetime):
                    run[key] = run[key].isoformat()

        return {
            "session_id": session_id,
            "agent_runs": runs,
        }

    except Exception as e:
        logger.error(f"Error getting agent runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CLIENT CALL HISTORY ENDPOINTS
# =============================================================================

@router.get("/client/{client_id}/calls", response_model=Dict[str, Any])
async def get_client_calls(
    client_id: str,
    loan_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get call history for a client (by lead_id or contact_id).

    Used by the Call Intelligence tab in ClientProfile.
    """
    try:
        # Query sessions for this client
        query = """
            SELECT cs.*,
                   (SELECT COUNT(*) FROM call_artifacts ca WHERE ca.session_id = cs.id) as artifact_count,
                   (SELECT COUNT(*) FROM call_artifacts ca WHERE ca.session_id = cs.id AND ca.approval_status = 'approved') as approved_count
            FROM call_sessions cs
            WHERE (cs.lead_id = :client_id OR cs.contact_id = :client_id)
        """
        params = {"client_id": client_id}

        if loan_id:
            query += " AND cs.loan_id = :loan_id"
            params["loan_id"] = loan_id

        query += " ORDER BY cs.created_at DESC LIMIT :limit"
        params["limit"] = limit

        result = db.execute(text(query), params)
        sessions = [dict(row._mapping) for row in result]

        # Convert types
        for session in sessions:
            for key in session:
                if isinstance(session[key], UUID):
                    session[key] = str(session[key])
                elif isinstance(session[key], datetime):
                    session[key] = session[key].isoformat()

        return {
            "client_id": client_id,
            "calls": sessions,
            "total": len(sessions),
        }

    except Exception as e:
        logger.error(f"Error getting client calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CI VOICE INTEGRATION
# =============================================================================

class ProcessCIRecordingRequest(BaseModel):
    """Request to process a CI Voice recording with AI agents."""
    recording_id: str = Field(..., description="UUID of the ci_call_recordings entry")
    run_agents: bool = Field(default=True, description="Whether to run AI agents")


@router.post("/process-ci-recording")
async def process_ci_recording(
    request: ProcessCIRecordingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Process an existing CI Voice recording with Call Monitoring AI agents.

    Use this to:
    - Process historical recordings that weren't automatically processed
    - Reprocess a recording with the latest agent prompts
    - Test the agent pipeline with a specific recording
    """
    try:
        # Check if recording exists and has transcription
        recording = db.execute(text("""
            SELECT r.id, r.status, r.loan_id, r.lead_id,
                   t.id as transcription_id, t.status as transcription_status
            FROM ci_call_recordings r
            LEFT JOIN ci_call_transcriptions t ON t.recording_id = r.id
            WHERE r.id = :recording_id
            ORDER BY t.created_at DESC
            LIMIT 1
        """), {"recording_id": request.recording_id}).fetchone()

        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")

        if not recording.transcription_id:
            raise HTTPException(
                status_code=400,
                detail="Recording has no transcription. Please transcribe first using /api/v1/ci-voice/recordings/{id}/transcribe"
            )

        if recording.transcription_status != 'completed':
            raise HTTPException(
                status_code=400,
                detail=f"Transcription not complete. Status: {recording.transcription_status}"
            )

        # Trigger the integration service
        from services.call_monitoring.ci_integration_service import CIIntegrationService

        service = CIIntegrationService(db)
        result = await service.process_completed_transcription(
            recording_id=request.recording_id,
            transcription_id=str(recording.transcription_id),
            run_agents=request.run_agents
        )

        return {
            "status": "success",
            "message": "Recording queued for AI agent processing",
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing CI recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ci-recordings")
async def list_ci_recordings(
    status: Optional[str] = Query(None, description="Filter by status: recorded, transcribed, analyzed"),
    loan_id: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List CI Voice recordings available for processing.

    Shows recordings that can be processed by Call Monitoring agents.
    """
    try:
        query = """
            SELECT
                r.id,
                r.external_call_id,
                r.direction,
                r.status,
                r.duration_seconds,
                r.started_at,
                r.loan_id,
                r.lead_id,
                t.id as transcription_id,
                t.status as transcription_status,
                t.word_count,
                cs.id as call_session_id,
                cs.status as session_status
            FROM ci_call_recordings r
            LEFT JOIN ci_call_transcriptions t ON t.recording_id = r.id
            LEFT JOIN call_sessions cs ON cs.recording_id = r.id
            WHERE 1=1
        """
        params = {"limit": limit}

        if status:
            query += " AND r.status = :status"
            params["status"] = status

        if loan_id:
            query += " AND r.loan_id = :loan_id"
            params["loan_id"] = loan_id

        if lead_id:
            query += " AND r.lead_id = :lead_id"
            params["lead_id"] = lead_id

        query += " ORDER BY r.started_at DESC LIMIT :limit"

        result = db.execute(text(query), params)
        recordings = []

        for row in result:
            rec = dict(row._mapping)
            # Convert UUIDs to strings
            for key in rec:
                if isinstance(rec[key], UUID):
                    rec[key] = str(rec[key])
                elif isinstance(rec[key], datetime):
                    rec[key] = rec[key].isoformat()

            # Add processing status
            rec["can_process"] = (
                rec.get("transcription_status") == "completed" and
                rec.get("call_session_id") is None
            )
            rec["already_processed"] = rec.get("call_session_id") is not None

            recordings.append(rec)

        return {
            "recordings": recordings,
            "total": len(recordings),
            "filters": {
                "status": status,
                "loan_id": loan_id,
                "lead_id": lead_id,
            }
        }

    except Exception as e:
        logger.error(f"Error listing CI recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CALL INTELLIGENCE PAGE ENDPOINTS
# =============================================================================

class ConvertToApplicationRequest(BaseModel):
    """Request to convert call data to a lead or loan application."""
    create_type: str = Field(..., description="'lead' or 'loan'")
    extracted_data: Dict[str, Any] = Field(..., description="Extracted borrower/loan data")
    notes: Optional[str] = None


@router.get("/sessions/{session_id}/live-transcript", response_model=Dict[str, Any])
async def get_live_transcript(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get live transcript for polling during active calls.

    Returns the current transcript state and any new chunks since last poll.
    Optimized for frequent polling during live calls.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        transcript_data = orchestrator.get_transcript(session_id)

        # Get any AI suggestions generated for this call
        suggestions_result = db.execute(text("""
            SELECT content, structured_data, created_at
            FROM call_artifacts
            WHERE session_id = :session_id
            AND artifact_type IN ('suggestion', 'prompt', 'compliance_reminder')
            ORDER BY created_at DESC
            LIMIT 10
        """), {"session_id": session_id})

        suggestions = []
        for row in suggestions_result:
            row_dict = dict(row._mapping)
            suggestions.append({
                "type": row_dict.get("structured_data", {}).get("type", "suggestion"),
                "text": row_dict.get("content"),
                "priority": row_dict.get("structured_data", {}).get("priority", "medium"),
                "created_at": row_dict["created_at"].isoformat() if row_dict.get("created_at") else None,
            })

        return {
            "session_id": session_id,
            "status": session.get("status"),
            "transcript": transcript_data.get("transcript", ""),
            "word_count": transcript_data.get("word_count", 0),
            "is_active": session.get("status") in ["active", "capturing"],
            "duration_seconds": session.get("duration_seconds"),
            "started_at": session.get("started_at"),
            "suggestions": suggestions,
            "participants": session.get("participants", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting live transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/convert-to-application", response_model=Dict[str, Any])
async def convert_to_application(
    session_id: str,
    request: ConvertToApplicationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Convert call session data into a lead or loan application.

    Extracts borrower information from call artifacts and creates
    a new lead or loan record pre-filled with the extracted data.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        data = request.extracted_data
        user_id = current_user.get("id", 1)

        if request.create_type == "lead":
            # Create a lead
            result = db.execute(text("""
                INSERT INTO leads (
                    first_name, last_name, email, phone,
                    source, status, loan_purpose, loan_amount,
                    property_type, notes, assigned_to, created_at, updated_at
                ) VALUES (
                    :first_name, :last_name, :email, :phone,
                    'call_conversion', 'new', :loan_purpose, :loan_amount,
                    :property_type, :notes, :assigned_to, NOW(), NOW()
                )
                RETURNING id
            """), {
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "loan_purpose": data.get("loan_purpose"),
                "loan_amount": float(str(data.get("loan_amount", "0")).replace(",", "").replace("$", "")) if data.get("loan_amount") else None,
                "property_type": data.get("property_type"),
                "notes": f"Converted from call session {session_id}. {request.notes or ''}",
                "assigned_to": user_id,
            })

            lead_id = result.fetchone()[0]
            db.commit()

            # Update session with conversion info
            db.execute(text("""
                UPDATE call_sessions
                SET lead_id = :lead_id,
                    metadata = jsonb_set(
                        COALESCE(metadata, '{}'::jsonb),
                        '{converted_to}',
                        '"lead"'
                    )
                WHERE id = :session_id
            """), {"lead_id": lead_id, "session_id": session_id})
            db.commit()

            return {
                "status": "success",
                "created_type": "lead",
                "created_id": lead_id,
                "message": f"Lead created successfully from call",
            }

        elif request.create_type == "loan":
            # Create a loan
            result = db.execute(text("""
                INSERT INTO loans (
                    borrower_first_name, borrower_last_name,
                    borrower_email, borrower_phone,
                    loan_purpose, loan_amount, property_type,
                    property_address, status, source,
                    loan_officer_id, created_at, updated_at
                ) VALUES (
                    :first_name, :last_name, :email, :phone,
                    :loan_purpose, :loan_amount, :property_type,
                    :property_address, 'lead', 'call_conversion',
                    :lo_id, NOW(), NOW()
                )
                RETURNING id
            """), {
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "loan_purpose": data.get("loan_purpose"),
                "loan_amount": float(str(data.get("loan_amount", "0")).replace(",", "").replace("$", "")) if data.get("loan_amount") else None,
                "property_type": data.get("property_type"),
                "property_address": data.get("property_address"),
                "lo_id": user_id,
            })

            loan_id = result.fetchone()[0]
            db.commit()

            # Update session with conversion info
            db.execute(text("""
                UPDATE call_sessions
                SET loan_id = :loan_id,
                    metadata = jsonb_set(
                        COALESCE(metadata, '{}'::jsonb),
                        '{converted_to}',
                        '"loan"'
                    )
                WHERE id = :session_id
            """), {"loan_id": loan_id, "session_id": session_id})
            db.commit()

            return {
                "status": "success",
                "created_type": "loan",
                "created_id": loan_id,
                "message": f"Loan application created successfully from call",
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="create_type must be 'lead' or 'loan'"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error converting call to application: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=Dict[str, Any])
async def get_call_metrics(
    days: int = Query(default=30, description="Number of days for metrics"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get call intelligence metrics for the dashboard.

    Returns:
    - Pending reviews count
    - Active calls count
    - Completed today
    - Conversion rate
    - Average call duration
    """
    try:
        # Get counts
        result = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('active', 'capturing')) as active_calls,
                COUNT(*) FILTER (WHERE status = 'completed' AND approval_status = 'pending') as pending_reviews,
                COUNT(*) FILTER (WHERE DATE(ended_at) = CURRENT_DATE) as completed_today,
                COUNT(*) FILTER (WHERE metadata->>'converted_to' IS NOT NULL AND ended_at >= NOW() - INTERVAL ':days days') as conversions,
                COUNT(*) FILTER (WHERE ended_at >= NOW() - INTERVAL ':days days') as total_completed,
                AVG(duration_seconds) FILTER (WHERE duration_seconds > 0) as avg_duration
            FROM call_sessions
            WHERE created_at >= NOW() - INTERVAL ':days days'
        """.replace(':days', str(days))))

        row = result.fetchone()
        metrics = dict(row._mapping) if row else {}

        # Calculate conversion rate
        total = metrics.get("total_completed", 0) or 1
        conversions = metrics.get("conversions", 0) or 0
        conversion_rate = round((conversions / total) * 100, 1)

        return {
            "active_calls": metrics.get("active_calls", 0) or 0,
            "pending_reviews": metrics.get("pending_reviews", 0) or 0,
            "completed_today": metrics.get("completed_today", 0) or 0,
            "conversion_rate": conversion_rate,
            "avg_duration_seconds": round(metrics.get("avg_duration", 0) or 0),
            "period_days": days,
        }

    except Exception as e:
        logger.error(f"Error getting call metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BACKGROUND TASK HELPERS
# =============================================================================

async def run_agents_background(
    db_url: str,
    session_id: str,
    agent_types: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    force_rerun: bool = False,
):
    """Background task to run agents."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            orchestrator = CallMonitoringOrchestrator(db)
            await orchestrator.run_agents(
                session_id=UUID(session_id),
                agent_types=agent_types,
                trigger="api_request",
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Background agent processing failed: {e}")
