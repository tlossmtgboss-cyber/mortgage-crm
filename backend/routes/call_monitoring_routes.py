"""
Call Monitoring Routes

API endpoints for the AI call monitoring system:
- Session management (create, update, end)
- Transcript handling (stream chunks, get full transcript)
- Agent processing and artifacts
- Review and approval workflow
- Artifact execution
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, BackgroundTasks,
    Query, Request, status, WebSocket, WebSocketDisconnect
)
from fastapi.responses import HTMLResponse
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
from sqlalchemy.exc import SQLAlchemyError

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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service not initialized",
        )

    try:
        return await _get_current_user(token=token, request=request, db=db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
# WORKFLOW RECONCILIATION HELPER
# =============================================================================

# Map CI artifact types to workflow action types for reconciliation.
# Only actionable artifacts that overlap with workflow-generated tasks are mapped;
# non-actionable types (summary, scribe_recap, etc.) are intentionally excluded.
_ARTIFACT_ACTION_MAP: Dict[str, str] = {
    "task": "task",
    "follow_up_draft": "email",
    "follow_up_call": "call",
    "document_request": "document_request",
    "scheduled_appointment": "appointment",
    "calendar_action": "appointment",
    "risk_flag": "condition",
}


async def _reconcile_ci_artifacts_with_workflows(
    db: Session,
    session_id: str,
    executed_artifacts: List[Dict[str, Any]],
    orchestrator: "CallMonitoringOrchestrator",
    user_id: str,
) -> None:
    """
    Best-effort reconciliation: after CI artifacts are executed, mark matching
    workflow_task_instances as completed so the workflow engine doesn't create
    duplicate outreach or trigger false SLA escalations.

    This is intentionally fire-and-forget — reconciliation failures are logged
    but never block the CI artifact response.
    """
    try:
        from services.workflow_reconciliation import reconcile_after_action
    except ImportError:
        # workflow_reconciliation service not yet deployed — skip silently
        logger.debug("workflow_reconciliation module not available; skipping CI reconciliation")
        return

    # Fetch session to get lead_id / loan_id
    try:
        session = orchestrator.get_session(session_id)
        if not session:
            logger.warning(f"CI reconciliation: session {session_id} not found")
            return

        session_lead_id = session.get("lead_id")
        session_loan_id = session.get("loan_id")

        # If there's no lead or loan association, there are no workflow tasks to reconcile
        if not session_lead_id and not session_loan_id:
            return

        reconciled_count = 0
        for artifact in executed_artifacts:
            artifact_type = artifact.get("artifact_type")
            action_type = _ARTIFACT_ACTION_MAP.get(artifact_type)
            if not action_type:
                # Non-actionable artifact type (summary, etc.) — nothing to reconcile
                continue

            try:
                await reconcile_after_action(
                    db=db,
                    action_type=action_type,
                    lead_id=session_lead_id,
                    loan_id=session_loan_id,
                    completed_by=user_id,
                    completion_source="call_intelligence",
                )
                reconciled_count += 1
            except Exception as e:
                logger.warning(
                    f"CI workflow reconciliation failed for artifact "
                    f"{artifact.get('artifact_id')} (type={artifact_type}): {e}"
                )

        if reconciled_count > 0:
            logger.info(
                f"CI workflow reconciliation: reconciled {reconciled_count} "
                f"action(s) for session {session_id}"
            )

    except Exception as e:
        logger.warning(f"CI workflow reconciliation failed for session {session_id}: {e}")


# =============================================================================
# CALLER IDENTIFICATION ENDPOINTS
# =============================================================================

class CallerLookupResponse(BaseModel):
    """Response from caller lookup."""
    found: bool
    client: Optional[Dict[str, Any]] = None
    source: Optional[str] = None  # lead, contact, loan_borrower


class CreateClientRequest(BaseModel):
    """Request to create a new client from a call."""
    phone: str
    name: str
    email: Optional[str] = None
    source: str = "inbound_call"
    metadata: Optional[Dict[str, Any]] = None


@router.get("/lookup-caller", response_model=CallerLookupResponse)
async def lookup_caller(
    phone: str = Query(..., description="Phone number to look up"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Look up a caller by phone number.

    Searches leads, contacts, and loan borrowers to find existing client records.
    Returns the most relevant match with their profile information.
    """
    try:
        # Normalize phone number - remove all non-digits
        normalized_phone = ''.join(filter(str.isdigit, phone))

        # Remove leading 1 if present (US country code)
        if len(normalized_phone) == 11 and normalized_phone.startswith('1'):
            normalized_phone = normalized_phone[1:]

        if len(normalized_phone) < 10:
            raise HTTPException(status_code=400, detail="Invalid phone number")

        # Create phone search patterns for different formats
        phone_patterns = [
            normalized_phone,
            f"+1{normalized_phone}",
            f"1{normalized_phone}",
            f"({normalized_phone[:3]}) {normalized_phone[3:6]}-{normalized_phone[6:]}",
            f"{normalized_phone[:3]}-{normalized_phone[3:6]}-{normalized_phone[6:]}",
        ]

        # Search in leads table first (most common for new calls)
        org_id = current_user.get("organization_id")
        lead_sql = """
            SELECT id, first_name, last_name, email, phone, status,
                   loan_amount, property_address, created_at
            FROM leads
            WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') LIKE :phone_pattern
        """
        if org_id:
            lead_sql += " AND organization_id = :org_id"
        lead_sql += " ORDER BY created_at DESC LIMIT 1"
        lead_query = text(lead_sql)

        lead_params = {"phone_pattern": f"%{normalized_phone[-10:]}"}
        if org_id:
            lead_params["org_id"] = org_id
        lead = db.execute(lead_query, lead_params).fetchone()

        if lead:
            return CallerLookupResponse(
                found=True,
                source="lead",
                client={
                    "id": str(lead.id),
                    "lead_id": str(lead.id),
                    "name": f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown",
                    "first_name": lead.first_name,
                    "last_name": lead.last_name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "loan_status": lead.status,
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
                    "property_address": lead.property_address,
                    "type": "lead",
                }
            )

        # Search in contacts table
        contact_sql = """
            SELECT id, first_name, last_name, email, phone, contact_type,
                   company, created_at
            FROM contacts
            WHERE REGEXP_REPLACE(phone, '[^0-9]', '', 'g') LIKE :phone_pattern
        """
        if org_id:
            contact_sql += " AND organization_id = :org_id"
        contact_sql += " ORDER BY created_at DESC LIMIT 1"
        contact_query = text(contact_sql)

        contact_params = {"phone_pattern": f"%{normalized_phone[-10:]}"}
        if org_id:
            contact_params["org_id"] = org_id
        contact = db.execute(contact_query, contact_params).fetchone()

        if contact:
            return CallerLookupResponse(
                found=True,
                source="contact",
                client={
                    "id": str(contact.id),
                    "contact_id": str(contact.id),
                    "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Unknown",
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "email": contact.email,
                    "phone": contact.phone,
                    "contact_type": contact.contact_type,
                    "company": contact.company,
                    "type": "contact",
                }
            )

        # Search in loans table (borrower info)
        loan_sql = """
            SELECT id, borrower_first_name, borrower_last_name, borrower_email,
                   borrower_phone, status, loan_amount, property_address
            FROM loans
            WHERE REGEXP_REPLACE(borrower_phone, '[^0-9]', '', 'g') LIKE :phone_pattern
        """
        if org_id:
            loan_sql += " AND organization_id = :org_id"
        loan_sql += " ORDER BY created_at DESC LIMIT 1"
        loan_query = text(loan_sql)

        loan_params = {"phone_pattern": f"%{normalized_phone[-10:]}"}
        if org_id:
            loan_params["org_id"] = org_id
        loan = db.execute(loan_query, loan_params).fetchone()

        if loan:
            return CallerLookupResponse(
                found=True,
                source="loan_borrower",
                client={
                    "id": str(loan.id),
                    "loan_id": str(loan.id),
                    "name": f"{loan.borrower_first_name or ''} {loan.borrower_last_name or ''}".strip() or "Unknown",
                    "first_name": loan.borrower_first_name,
                    "last_name": loan.borrower_last_name,
                    "email": loan.borrower_email,
                    "phone": loan.borrower_phone,
                    "loan_status": loan.status,
                    "loan_amount": float(loan.loan_amount) if loan.loan_amount else None,
                    "property_address": loan.property_address,
                    "type": "loan_borrower",
                }
            )

        # Not found
        return CallerLookupResponse(found=False, client=None, source=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Caller lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Lookup failed")


@router.post("/create-client", response_model=Dict[str, Any])
async def create_client_from_call(
    request: CreateClientRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new lead/client from an inbound call.

    Creates a lead record for a new caller that wasn't found in the database.
    """
    try:
        # Normalize phone
        normalized_phone = ''.join(filter(str.isdigit, request.phone))
        if len(normalized_phone) == 10:
            formatted_phone = f"({normalized_phone[:3]}) {normalized_phone[3:6]}-{normalized_phone[6:]}"
        else:
            formatted_phone = request.phone

        # Parse name into first/last
        name_parts = request.name.strip().split(' ', 1)
        first_name = name_parts[0] if name_parts else "Unknown"
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Get current user ID for assignment
        user_id = current_user["id"]

        # Insert new lead
        insert_query = text("""
            INSERT INTO leads (
                name, first_name, last_name, email, phone,
                source, status, assigned_to, created_at, updated_at
            ) VALUES (
                :name, :first_name, :last_name, :email, :phone,
                :source, 'new', :assigned_to, NOW(), NOW()
            )
            RETURNING id, first_name, last_name, email, phone, source, status, created_at
        """)

        result = db.execute(insert_query, {
            "name": f"{first_name} {last_name}".strip() or "Unknown",
            "first_name": first_name,
            "last_name": last_name,
            "email": request.email,
            "phone": formatted_phone,
            "source": request.source,
            "assigned_to": user_id,
        }).fetchone()

        db.commit()

        return {
            "success": True,
            "id": str(result.id),
            "lead_id": str(result.id),
            "client": {
                "id": str(result.id),
                "lead_id": str(result.id),
                "name": f"{result.first_name} {result.last_name}".strip(),
                "first_name": result.first_name,
                "last_name": result.last_name,
                "email": result.email,
                "phone": result.phone,
                "source": result.source,
                "loan_status": result.status,
                "type": "lead",
                "is_new": True,
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create client: {e}")
        raise HTTPException(status_code=500, detail="Failed to create client")


@router.get("/search-clients", response_model=Dict[str, Any])
async def search_clients(
    name: Optional[str] = Query(None, description="Client name to search for"),
    email: Optional[str] = Query(None, description="Email to search for"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Search for clients by name or email.

    Used by automatic client detection during calls when phone number
    doesn't match but a name is mentioned in the conversation.
    """
    try:
        if not name and not email:
            return {"found": False, "clients": []}

        org_id = current_user.get("organization_id")
        org_filter = "AND organization_id = :org_id" if org_id else ""
        clients = []

        # Search leads by name
        if name:
            name_parts = name.strip().split()
            if len(name_parts) >= 2:
                # Full name search
                lead_name_sql = """
                    SELECT id, first_name, last_name, email, phone, status, created_at
                    FROM leads
                    WHERE LOWER(first_name) LIKE LOWER(:first_pattern)
                      AND LOWER(last_name) LIKE LOWER(:last_pattern)
                """
                if org_id:
                    lead_name_sql += " AND organization_id = :org_id"
                lead_name_sql += " ORDER BY created_at DESC LIMIT 5"
                lead_params = {
                    "first_pattern": f"{name_parts[0]}%",
                    "last_pattern": f"{name_parts[1]}%",
                }
                if org_id:
                    lead_params["org_id"] = org_id
                results = db.execute(text(lead_name_sql), lead_params).fetchall()
            else:
                # Single name search (first or last)
                lead_single_sql = """
                    SELECT id, first_name, last_name, email, phone, status, created_at
                    FROM leads
                    WHERE (LOWER(first_name) LIKE LOWER(:pattern)
                       OR LOWER(last_name) LIKE LOWER(:pattern))
                """
                if org_id:
                    lead_single_sql += " AND organization_id = :org_id"
                lead_single_sql += " ORDER BY created_at DESC LIMIT 5"
                lead_params = {
                    "pattern": f"{name}%",
                }
                if org_id:
                    lead_params["org_id"] = org_id
                results = db.execute(text(lead_single_sql), lead_params).fetchall()

            for r in results:
                clients.append({
                    "id": str(r.id),
                    "lead_id": str(r.id),
                    "name": f"{r.first_name} {r.last_name}".strip(),
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "email": r.email,
                    "phone": r.phone,
                    "loan_status": r.status,
                    "type": "lead",
                })

        # Search contacts by name
        if name and len(clients) < 5:
            name_parts = name.strip().split()
            if len(name_parts) >= 2:
                contact_name_sql = """
                    SELECT id, first_name, last_name, email, phone, created_at
                    FROM contacts
                    WHERE LOWER(first_name) LIKE LOWER(:first_pattern)
                      AND LOWER(last_name) LIKE LOWER(:last_pattern)
                """
                if org_id:
                    contact_name_sql += " AND organization_id = :org_id"
                contact_name_sql += " ORDER BY created_at DESC LIMIT 5"
                contact_params = {
                    "first_pattern": f"{name_parts[0]}%",
                    "last_pattern": f"{name_parts[1]}%",
                }
                if org_id:
                    contact_params["org_id"] = org_id
                results = db.execute(text(contact_name_sql), contact_params).fetchall()
            else:
                contact_single_sql = """
                    SELECT id, first_name, last_name, email, phone, created_at
                    FROM contacts
                    WHERE (LOWER(first_name) LIKE LOWER(:pattern)
                       OR LOWER(last_name) LIKE LOWER(:pattern))
                """
                if org_id:
                    contact_single_sql += " AND organization_id = :org_id"
                contact_single_sql += " ORDER BY created_at DESC LIMIT 5"
                contact_params = {
                    "pattern": f"{name}%",
                }
                if org_id:
                    contact_params["org_id"] = org_id
                results = db.execute(text(contact_single_sql), contact_params).fetchall()

            for r in results:
                clients.append({
                    "id": str(r.id),
                    "contact_id": str(r.id),
                    "name": f"{r.first_name} {r.last_name}".strip(),
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "email": r.email,
                    "phone": r.phone,
                    "type": "contact",
                })

        # Search by email if provided
        if email:
            email_sql = """
                SELECT id, first_name, last_name, email, phone, status
                FROM leads
                WHERE LOWER(email) = LOWER(:email)
            """
            if org_id:
                email_sql += " AND organization_id = :org_id"
            email_sql += " LIMIT 1"
            email_query = text(email_sql)
            email_params = {"email": email}
            if org_id:
                email_params["org_id"] = org_id
            result = db.execute(email_query, email_params).fetchone()
            if result:
                clients.insert(0, {
                    "id": str(result.id),
                    "lead_id": str(result.id),
                    "name": f"{result.first_name} {result.last_name}".strip(),
                    "email": result.email,
                    "phone": result.phone,
                    "loan_status": result.status,
                    "type": "lead",
                })

        return {
            "found": len(clients) > 0,
            "clients": clients,
            "count": len(clients),
        }

    except Exception as e:
        logger.error(f"Failed to search clients: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}", response_model=Dict[str, Any])
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get call session details."""
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/sessions/{session_id}", response_model=Dict[str, Any])
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update call session details."""
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
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
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update session status and set transcript if provided
        now = datetime.now(timezone.utc)
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
    except SQLAlchemyError as e:
        logger.error(f"Error ending session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


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
        # Build query with org_id scoping
        org_id = current_user.get("organization_id")
        query = "SELECT * FROM call_sessions WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM call_sessions WHERE 1=1"
        params = {}

        if org_id:
            query += " AND organization_id = :org_id"
            count_query += " AND organization_id = :org_id"
            params["org_id"] = org_id

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}/transcript", response_model=Dict[str, Any])
async def get_transcript(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the full transcript for a session."""
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
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
    except SQLAlchemyError as e:
        logger.error(f"Error getting transcript: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
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
    except SQLAlchemyError as e:
        logger.error(f"Error running agents: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/artifacts/approve", response_model=Dict[str, Any])
async def approve_artifacts(
    session_id: str,
    request: ApproveArtifactsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Approve selected artifacts."""
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/artifacts/reject", response_model=Dict[str, Any])
async def reject_artifacts(
    session_id: str,
    request: RejectArtifactsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Reject selected artifacts."""
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
    After execution, reconciles with workflow task instances to prevent duplicate
    outreach and false escalations.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

        results = await orchestrator.execute_approved_artifacts(
            session_id=session_id,
            user_id=str(current_user.get("id")),
        )

        executed_count = len(results.get("executed", []))

        # Best-effort workflow reconciliation: mark matching workflow_task_instances
        # as completed so the workflow engine doesn't create duplicate outreach or
        # trigger false SLA escalations for work already done via CI artifacts.
        if executed_count > 0:
            await _reconcile_ci_artifacts_with_workflows(
                db=db,
                session_id=session_id,
                executed_artifacts=results.get("executed", []),
                orchestrator=orchestrator,
                user_id=str(current_user.get("id")),
            )

        return {
            "status": "success",
            "session_id": session_id,
            "executed_count": executed_count,
            "results": results,
        }

    except SQLAlchemyError as e:
        logger.error(f"Error executing artifacts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        review_data = orchestrator.get_review_data(session_id)

        if not review_data:
            raise HTTPException(status_code=404, detail="Session not found")

        return review_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting review data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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

    This approves selected artifacts, triggers execution, and reconciles with
    workflow task instances to prevent duplicate outreach.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
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

        # Best-effort workflow reconciliation after artifact execution
        if executed_count > 0:
            await _reconcile_ci_artifacts_with_workflows(
                db=db,
                session_id=session_id,
                executed_artifacts=results.get("executed", []),
                orchestrator=orchestrator,
                user_id=user_id,
            )

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        # Query sessions for this client (scoped to org)
        org_id = current_user.get("organization_id")
        query = """
            SELECT cs.*,
                   (SELECT COUNT(*) FROM call_artifacts ca WHERE ca.session_id = cs.id) as artifact_count,
                   (SELECT COUNT(*) FROM call_artifacts ca WHERE ca.session_id = cs.id AND ca.approval_status = 'approved') as approved_count
            FROM call_sessions cs
            WHERE (cs.lead_id = :client_id OR cs.contact_id = :client_id)
        """
        params = {"client_id": client_id}

        if org_id:
            query += " AND cs.organization_id = :org_id"
            params["org_id"] = org_id

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
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# LOAN CALL HISTORY
# =============================================================================

@router.get("/loan/{loan_id}/calls", response_model=Dict[str, Any])
async def get_loan_calls(
    loan_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get call history for a loan from the call_logs table.

    Used by the Loan detail view to show call activity on a file.
    """
    try:
        org_id = current_user.get("organization_id")
        query = """
            SELECT cl.id, cl.call_sid, cl.contact_phone AS from_number,
                   cl.caller_id_used AS to_number,
                   CASE WHEN cl.agent_id = :user_id THEN 'outbound' ELSE 'inbound' END AS direction,
                   cl.outcome AS status, cl.duration_seconds AS duration,
                   cl.recording_url, cl.transcript_text, cl.transcript_status,
                   cl.created_at
            FROM call_logs cl
            WHERE cl.loan_id = :loan_id
        """
        params: Dict[str, Any] = {
            "loan_id": loan_id,
            "user_id": current_user.get("id"),
        }

        if org_id:
            query += " AND cl.organization_id = :org_id"
            params["org_id"] = org_id

        # Get total count
        count_result = db.execute(
            text(f"SELECT COUNT(*) FROM call_logs cl WHERE cl.loan_id = :loan_id"
                 + (" AND cl.organization_id = :org_id" if org_id else "")),
            params,
        )
        total = count_result.scalar() or 0

        query += " ORDER BY cl.created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = db.execute(text(query), params)
        calls = [dict(row._mapping) for row in result]

        # Convert types for JSON serialization
        for call in calls:
            for key in call:
                if isinstance(call[key], UUID):
                    call[key] = str(call[key])
                elif isinstance(call[key], datetime):
                    call[key] = call[key].isoformat()

        return {
            "loan_id": loan_id,
            "calls": calls,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error getting loan calls: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        # Check if recording exists and has transcription (scoped to user's org)
        org_id = current_user.get("organization_id")
        rec_params = {"recording_id": request.recording_id}
        rec_sql = """
            SELECT r.id, r.status, r.loan_id, r.lead_id,
                   t.id as transcription_id, t.status as transcription_status
            FROM ci_call_recordings r
            LEFT JOIN users u ON u.id = r.agent_user_id
            LEFT JOIN ci_call_transcriptions t ON t.recording_id = r.id
            WHERE r.id = :recording_id
        """
        if org_id:
            rec_sql += " AND u.organization_id = :org_id"
            rec_params["org_id"] = org_id
        rec_sql += " ORDER BY t.created_at DESC LIMIT 1"
        recording = db.execute(text(rec_sql), rec_params).fetchone()

        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")

        if not recording.transcription_id:
            raise HTTPException(
                status_code=400,
                detail="Recording has no transcription. Please transcribe first using /api/v1/conversation-intelligence/recordings/{id}/transcribe"
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        org_id = current_user.get("organization_id")
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

        if org_id:
            query += " AND r.organization_id = :org_id"
            params["org_id"] = org_id

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
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
    except SQLAlchemyError as e:
        logger.error(f"Error getting live transcript: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        data = request.extracted_data
        user_id = current_user["id"]

        if request.create_type == "lead":
            # Create a lead
            result = db.execute(text("""
                INSERT INTO leads (
                    name, first_name, last_name, email, phone,
                    source, status, loan_purpose, loan_amount,
                    property_type, notes, assigned_to, created_at, updated_at
                ) VALUES (
                    :name, :first_name, :last_name, :email, :phone,
                    'call_conversion', 'new', :loan_purpose, :loan_amount,
                    :property_type, :notes, :assigned_to, NOW(), NOW()
                )
                RETURNING id
            """), {
                "name": f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "Unknown",
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        # Get counts (scoped to org)
        org_id = current_user.get("organization_id")
        metrics_params = {"days": days}
        metrics_sql = """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('active', 'capturing')) as active_calls,
                COUNT(*) FILTER (WHERE status = 'completed' AND approval_status = 'pending') as pending_reviews,
                COUNT(*) FILTER (WHERE DATE(ended_at) = CURRENT_DATE) as completed_today,
                COUNT(*) FILTER (WHERE metadata->>'converted_to' IS NOT NULL AND ended_at >= NOW() - INTERVAL '1 day' * :days) as conversions,
                COUNT(*) FILTER (WHERE ended_at >= NOW() - INTERVAL '1 day' * :days) as total_completed,
                AVG(duration_seconds) FILTER (WHERE duration_seconds > 0) as avg_duration
            FROM call_sessions
            WHERE created_at >= NOW() - INTERVAL '1 day' * :days
        """
        if org_id:
            metrics_sql += " AND organization_id = :org_id"
            metrics_params["org_id"] = org_id
        result = db.execute(text(metrics_sql), metrics_params)

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
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ARTIFACT SHARING ENDPOINTS
# =============================================================================

class CreateShareLinkRequest(BaseModel):
    """Request to create a shareable link for an artifact."""
    expires_in_days: int = Field(default=7, ge=1, le=90, description="Days until link expires")
    title_override: Optional[str] = Field(None, description="Custom title for shared view")
    description_override: Optional[str] = Field(None, description="Custom description")


@router.post("/artifacts/{artifact_id}/share", response_model=Dict[str, Any])
async def create_artifact_share_link(
    artifact_id: str,
    request: CreateShareLinkRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a shareable link for an artifact (e.g., calculator result).

    The generated link can be shared with borrowers during video calls
    or via SMS/email to show them calculation results.
    """
    try:
        from services.calculator_share_service import CalculatorShareService

        service = CalculatorShareService(db)
        result = service.create_share_link(
            artifact_id=artifact_id,
            user_id=current_user.get("id"),
            expires_in_days=request.expires_in_days,
            title_override=request.title_override,
            description_override=request.description_override,
            organization_id=current_user.get("organization_id"),
        )

        # Build full URL
        base_url = str(http_request.base_url).rstrip("/")
        result["full_url"] = f"{base_url}{result['share_url']}"

        return {
            "status": "success",
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error creating share link: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/shared/{share_token}", response_model=Dict[str, Any])
async def get_shared_artifact(
    share_token: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Get a shared artifact by its token (PUBLIC endpoint - no auth required).

    This endpoint is used by the public SharedCalculator page to display
    calculator results to borrowers.
    """
    try:
        from services.calculator_share_service import CalculatorShareService

        # Get viewer info for tracking
        viewer_ip = http_request.client.host if http_request.client else None
        viewer_user_agent = http_request.headers.get("user-agent")

        service = CalculatorShareService(db)
        artifact = service.get_shared_artifact(
            share_token=share_token,
            viewer_ip=viewer_ip,
            viewer_user_agent=viewer_user_agent,
        )

        if not artifact:
            raise HTTPException(
                status_code=404,
                detail="Share link not found, expired, or deactivated"
            )

        return {
            "status": "success",
            **artifact
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shared artifact: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/embed/{share_token}", response_class=HTMLResponse)
async def get_calculator_embed(
    share_token: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Get embeddable HTML for a calculator result (for iframe embedding).

    Used by the portal Video OS for screen sharing calculator results
    during video calls.
    """
    from fastapi.responses import HTMLResponse

    try:
        from services.calculator_share_service import CalculatorShareService, generate_embed_html

        viewer_ip = http_request.client.host if http_request.client else None
        viewer_user_agent = http_request.headers.get("user-agent")

        service = CalculatorShareService(db)
        artifact = service.get_shared_artifact(
            share_token=share_token,
            viewer_ip=viewer_ip,
            viewer_user_agent=viewer_user_agent,
        )

        if not artifact:
            return HTMLResponse(
                content="<html><body><h1>Link expired or not found</h1></body></html>",
                status_code=404
            )

        base_url = str(http_request.base_url).rstrip("/")
        html = generate_embed_html(artifact, base_url)

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating embed: {e}")
        return HTMLResponse(
            content="<html><body><h1>Error loading calculator</h1><p>An internal error occurred.</p></body></html>",
            status_code=500
        )


@router.delete("/artifacts/{artifact_id}/share/{share_token}", response_model=Dict[str, Any])
async def deactivate_share_link(
    artifact_id: str,
    share_token: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Deactivate a share link.

    Only the creator or admins can deactivate links.
    """
    try:
        from services.calculator_share_service import CalculatorShareService

        service = CalculatorShareService(db)
        success = service.deactivate_share(
            share_token=share_token,
            user_id=current_user.get("id"),
            organization_id=current_user.get("organization_id"),
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Share link not found or you don't have permission to deactivate it"
            )

        return {
            "status": "success",
            "message": "Share link deactivated",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating share link: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/artifacts/{artifact_id}/shares", response_model=Dict[str, Any])
async def get_artifact_shares(
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all share links for an artifact.
    """
    try:
        from services.calculator_share_service import CalculatorShareService

        service = CalculatorShareService(db)
        shares = service.get_shares_for_artifact(
            artifact_id,
            organization_id=current_user.get("organization_id"),
        )

        return {
            "status": "success",
            "artifact_id": artifact_id,
            "shares": shares,
            "total": len(shares),
        }

    except Exception as e:
        logger.error(f"Error getting artifact shares: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/my-shares", response_model=Dict[str, Any])
async def get_my_shares(
    include_expired: bool = Query(False, description="Include expired links"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all share links created by the current user.
    """
    try:
        from services.calculator_share_service import CalculatorShareService

        service = CalculatorShareService(db)
        shares = service.get_user_shares(
            user_id=current_user.get("id"),
            include_expired=include_expired,
            limit=limit,
        )

        return {
            "status": "success",
            "shares": shares,
            "total": len(shares),
        }

    except Exception as e:
        logger.error(f"Error getting user shares: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CALL INTELLIGENCE EXPANSION - STACKED NOTES & REVIEW TASKS
# =============================================================================

class CreateReviewTaskRequest(BaseModel):
    """Request to create a review task from JR LO or Underwriter analysis."""
    task_type: str = Field(..., description="Type of task: 'uw_review', 'jrlo_5c_review', etc.")
    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Task description")
    priority: str = Field(default="medium", description="Task priority: low, medium, high")
    assigned_role: Optional[str] = Field(None, description="Role to assign: 'pa', 'lo', 'processor'")


class CompleteUWReviewRequest(BaseModel):
    """Request to complete UW review and create PA task."""
    summary: str = Field(..., description="Summary of UW review findings")
    items_addressed: List[str] = Field(default=[], description="List of items addressed")
    create_pa_task: bool = Field(default=True, description="Whether to create a PA task")
    pa_task_title: Optional[str] = Field(None, description="Optional custom PA task title")


@router.get("/client/{client_id}/stacked-notes", response_model=Dict[str, Any])
async def get_stacked_notes(
    client_id: str,
    limit: int = Query(default=100, ge=1, le=500, description="Maximum notes to return"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all stacked notes for a client across all calls.

    Notes are sorted newest first (new notes on top, prior notes pushed down).
    Each note includes date stamp, source (Scribe/JR LO/Underwriter), and call mode.
    """
    try:
        # Get all sessions for this client (via loan_id or lead_id, scoped to org)
        org_id = current_user.get("organization_id")
        sessions_sql = """
            SELECT DISTINCT cs.id as session_id, cs.call_mode, cs.started_at, cs.ended_at
            FROM call_sessions cs
            WHERE (cs.loan_id = :client_id OR cs.lead_id = :client_id)
        """
        if org_id:
            sessions_sql += " AND cs.organization_id = :org_id"
        sessions_sql += " ORDER BY cs.started_at DESC"
        session_params = {"client_id": client_id}
        if org_id:
            session_params["org_id"] = org_id
        sessions_result = db.execute(text(sessions_sql), session_params)
        sessions = [dict(row._mapping) for row in sessions_result]

        if not sessions:
            return {
                "status": "success",
                "client_id": client_id,
                "notes": [],
                "total": 0,
                "message": "No call sessions found for this client"
            }

        session_ids = [str(s["session_id"]) for s in sessions]

        # Get all stacked notes and related artifacts
        notes_query = text("""
            SELECT
                ca.id,
                ca.session_id,
                ca.artifact_type,
                ca.content,
                ca.structured_data,
                ca.created_at,
                cs.call_mode,
                cs.started_at as call_started_at,
                cs.ended_at as call_ended_at
            FROM call_artifacts ca
            JOIN call_sessions cs ON cs.id = ca.session_id
            WHERE ca.session_id = ANY(:session_ids)
            AND ca.artifact_type IN (
                'stacked_note', 'scribe_recap', 'summary',
                'uw_note', 'uw_review_item',
                'five_c_credit', 'five_c_collateral', 'five_c_capacity',
                'five_c_characteristics', 'five_c_cash'
            )
            ORDER BY ca.created_at DESC
            LIMIT :limit
        """)

        notes_result = db.execute(notes_query, {
            "session_ids": session_ids,
            "limit": limit
        })

        notes = []
        for row in notes_result:
            row_dict = dict(row._mapping)

            # Determine source based on artifact type
            artifact_type = row_dict.get("artifact_type", "")
            if artifact_type in ["scribe_recap", "summary"]:
                source = "scribe"
            elif artifact_type.startswith("five_c_"):
                source = "jrlo"
            elif artifact_type in ["uw_note", "uw_review_item"]:
                source = "underwriter"
            elif artifact_type == "stacked_note":
                source = row_dict.get("structured_data", {}).get("source", "unknown")
            else:
                source = "unknown"

            notes.append({
                "id": str(row_dict["id"]),
                "session_id": str(row_dict["session_id"]),
                "artifact_type": artifact_type,
                "content": row_dict.get("content"),
                "structured_data": row_dict.get("structured_data", {}),
                "source": source,
                "call_mode": row_dict.get("call_mode"),
                "created_at": row_dict["created_at"].isoformat() if row_dict.get("created_at") else None,
                "call_started_at": row_dict["call_started_at"].isoformat() if row_dict.get("call_started_at") else None,
                "call_ended_at": row_dict["call_ended_at"].isoformat() if row_dict.get("call_ended_at") else None,
            })

        return {
            "status": "success",
            "client_id": client_id,
            "notes": notes,
            "total": len(notes),
            "sessions_count": len(sessions),
        }

    except Exception as e:
        logger.error(f"Error getting stacked notes for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/complete-uw-review", response_model=Dict[str, Any])
async def complete_uw_review(
    session_id: str,
    request: CompleteUWReviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark UW review as complete and optionally create a Production Assistant task.

    This endpoint is called when the underwriter completes their review checklist.
    It updates all UW review items as addressed and creates a PA task if requested.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        user_id = current_user["id"]

        # Mark all UW review items as completed for this session
        db.execute(text("""
            UPDATE call_artifacts
            SET execution_status = 'completed',
                structured_data = jsonb_set(
                    COALESCE(structured_data, '{}'::jsonb),
                    '{addressed_at}',
                    to_jsonb(NOW()::text)
                )
            WHERE session_id = :session_id
            AND artifact_type = 'uw_review_item'
            AND (execution_status IS NULL OR execution_status != 'completed')
        """), {"session_id": session_id})

        # Create UW completion artifact
        db.execute(text("""
            INSERT INTO call_artifacts (
                session_id, artifact_type, content, structured_data,
                execution_status, created_at
            ) VALUES (
                :session_id, 'uw_review_completed', :summary,
                :structured_data, 'completed', NOW()
            )
        """), {
            "session_id": session_id,
            "summary": request.summary,
            "structured_data": json.dumps({
                "items_addressed": request.items_addressed,
                "completed_by": user_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        })

        pa_task_id = None

        # Create PA task if requested
        if request.create_pa_task:
            loan_id = session.get("loan_id")

            if loan_id:
                # Find PA user for this loan
                pa_result = db.execute(text("""
                    SELECT u.id
                    FROM users u
                    JOIN loans l ON (l.processor_id = u.id OR u.role = 'production_assistant')
                    WHERE l.id = :loan_id
                    LIMIT 1
                """), {"loan_id": loan_id})
                pa_row = pa_result.fetchone()
                pa_user_id = pa_row[0] if pa_row else None
            else:
                pa_user_id = None

            # Create the task
            task_title = request.pa_task_title or f"Review UW Notes - Call {session_id[:8]}"

            task_result = db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority,
                    task_type, source, source_id,
                    loan_id, assigned_to, created_by, created_at
                ) VALUES (
                    :title, :description, 'pending', 'medium',
                    'uw_review', 'underwriter_agent', :session_id,
                    :loan_id, :assigned_to, :created_by, NOW()
                )
                RETURNING id
            """), {
                "title": task_title,
                "description": f"UW Review completed. Summary: {request.summary}",
                "session_id": session_id,
                "loan_id": loan_id,
                "assigned_to": pa_user_id,
                "created_by": user_id,
            })

            task_row = task_result.fetchone()
            pa_task_id = task_row[0] if task_row else None

        db.commit()

        return {
            "status": "success",
            "session_id": session_id,
            "items_addressed_count": len(request.items_addressed),
            "pa_task_created": request.create_pa_task,
            "pa_task_id": pa_task_id,
            "message": "UW review completed successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing UW review for session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/create-review-task", response_model=Dict[str, Any])
async def create_review_task(
    session_id: str,
    request: CreateReviewTaskRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a review task from JR LO or Underwriter analysis.

    This endpoint allows agents to create tasks for items that need attention,
    such as 5 C's review items or underwriting conditions.
    """
    try:
        orchestrator = CallMonitoringOrchestrator(db, organization_id=current_user.get("organization_id"))
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        user_id = current_user["id"]
        loan_id = session.get("loan_id")

        # Determine assigned user based on role
        assigned_to = None
        if request.assigned_role and loan_id:
            role_mapping = {
                "pa": "production_assistant",
                "lo": "loan_officer",
                "processor": "processor",
            }
            target_role = role_mapping.get(request.assigned_role)

            if target_role:
                # Try to find user with that role for this loan
                user_result = db.execute(text("""
                    SELECT u.id
                    FROM users u
                    LEFT JOIN loans l ON (
                        (l.loan_officer_id = u.id AND :role = 'loan_officer')
                        OR (l.processor_id = u.id AND :role = 'processor')
                        OR (u.role = :role)
                    )
                    WHERE l.id = :loan_id OR u.role = :role
                    LIMIT 1
                """), {"loan_id": loan_id, "role": target_role})
                user_row = user_result.fetchone()
                assigned_to = user_row[0] if user_row else None

        # Map priority string to appropriate value
        priority_map = {"low": "low", "medium": "medium", "high": "high"}
        priority = priority_map.get(request.priority, "medium")

        # Create the task
        task_result = db.execute(text("""
            INSERT INTO tasks (
                title, description, status, priority,
                task_type, source, source_id,
                loan_id, assigned_to, created_by, created_at
            ) VALUES (
                :title, :description, 'pending', :priority,
                :task_type, :source, :session_id,
                :loan_id, :assigned_to, :created_by, NOW()
            )
            RETURNING id
        """), {
            "title": request.title,
            "description": request.description,
            "priority": priority,
            "task_type": request.task_type,
            "source": f"{request.task_type}_agent",
            "session_id": session_id,
            "loan_id": loan_id,
            "assigned_to": assigned_to,
            "created_by": user_id,
        })

        task_row = task_result.fetchone()
        task_id = task_row[0] if task_row else None

        db.commit()

        return {
            "status": "success",
            "task_id": task_id,
            "session_id": session_id,
            "task_type": request.task_type,
            "assigned_to": assigned_to,
            "message": f"Review task '{request.title}' created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating review task for session {session_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# RECORDING PLAYBACK (MOBILE APP)
# =============================================================================

class TranscriptSegmentResponse(BaseModel):
    """A single transcript segment with timing for playback sync."""
    speaker: Optional[str] = None
    speaker_label: Optional[str] = None
    text: str
    start_time_ms: int
    end_time_ms: int
    confidence: Optional[float] = None


class RecordingPlaybackResponse(BaseModel):
    """Full recording playback payload with synced transcript."""
    call_id: str
    source: str  # 'call_session', 'ci_recording', 'vapi', 'dialer'
    recording_url: Optional[str] = None
    stereo_recording_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    transcript_text: Optional[str] = None
    transcript_segments: Optional[List[TranscriptSegmentResponse]] = None
    summary: Optional[str] = None
    participants: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[str] = None


def _maybe_presign_url(url: Optional[str], org_id: Optional[int] = None) -> Optional[str]:
    """
    If the URL points to an S3/R2 bucket, generate a presigned download URL
    with 1-hour expiry.  Otherwise return the URL unchanged.
    """
    if not url:
        return None

    # Detect S3/R2 storage paths (s3://, bucket references, or internal storage keys)
    is_s3 = (
        url.startswith("s3://")
        or ".s3." in url
        or ".r2." in url
        or url.startswith("recordings/")
        or url.startswith("call-recordings/")
    )

    if not is_s3:
        return url

    try:
        from services.perennia_s3_service import PerenniaS3Service

        s3_service = PerenniaS3Service()

        # Extract storage key from full S3 URL or use as-is if already a key
        storage_key = url
        if url.startswith("s3://"):
            # s3://bucket-name/path/to/file -> path/to/file
            parts = url.replace("s3://", "").split("/", 1)
            storage_key = parts[1] if len(parts) > 1 else parts[0]
        elif "amazonaws.com/" in url or ".r2." in url:
            # https://bucket.s3.amazonaws.com/key -> key
            storage_key = url.split(".com/", 1)[-1].split("?")[0]

        result = s3_service.get_presigned_download_url(
            storage_key=storage_key,
            expires_in=3600,  # 1 hour
            organization_id=org_id,
        )
        if result.get("success"):
            return result["presigned_url"]

        logger.warning(f"Presigned URL generation failed: {result}")
        return url
    except Exception as e:
        logger.warning(f"Could not generate presigned URL for {url[:60]}...: {e}")
        return url


def _parse_transcript_segments_from_text(transcript: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """
    Best-effort parse of timestamped transcript text into segments.

    Supports common formats:
      [00:01:23] Speaker A: Hello world
      [00:01:23 - 00:01:30] Speaker A: Hello world
      (0:01:23) Speaker A: Hello world
    """
    if not transcript:
        return None

    import re
    # Match lines like: [HH:MM:SS] Speaker: text  or  [MM:SS] Speaker: text
    pattern = re.compile(
        r'[\[\(]'
        r'(?:(\d{1,2}):)?(\d{1,2}):(\d{2})'       # start time  HH:MM:SS or MM:SS
        r'(?:\s*[-–]\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2}))?'  # optional end time
        r'[\]\)]\s*'
        r'(?:([^:]{1,40}):\s*)?'                     # optional speaker label
        r'(.+)'                                       # text
    )

    segments = []
    for match in pattern.finditer(transcript):
        h1, m1, s1 = match.group(1) or "0", match.group(2), match.group(3)
        start_ms = (int(h1) * 3600 + int(m1) * 60 + int(s1)) * 1000

        h2, m2, s2 = match.group(4), match.group(5), match.group(6)
        if m2 and s2:
            end_ms = (int(h2 or "0") * 3600 + int(m2) * 60 + int(s2)) * 1000
        else:
            end_ms = start_ms + 5000  # default 5-second segment

        segments.append({
            "speaker": (match.group(7) or "").strip() or None,
            "speaker_label": None,
            "text": match.group(8).strip(),
            "start_time_ms": start_ms,
            "end_time_ms": end_ms,
            "confidence": None,
        })

    return segments if segments else None


@router.get(
    "/calls/{call_id}/recording",
    response_model=RecordingPlaybackResponse,
    summary="Get recording with synced transcript for playback",
)
async def get_recording_playback(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve a call recording URL and its synced transcript for mobile playback.

    Searches across all call storage:
    1. call_sessions -> ci_call_recordings (richest data, has timed segments)
    2. vapi_calls
    3. call_logs (dialer)

    If the recording is stored in S3/R2, a presigned URL (1-hour expiry) is
    returned.  If the transcript has per-segment timestamps, they are returned
    in ``transcript_segments`` for playback sync on the mobile player.
    """
    org_id = current_user.get("organization_id")

    # -----------------------------------------------------------------
    # 1. Try call_sessions + ci_call_recordings (best data source)
    # -----------------------------------------------------------------
    session_sql = """
        SELECT
            cs.id              AS session_id,
            cs.full_transcript,
            cs.duration_seconds,
            cs.started_at,
            cs.participants,
            r.recording_url,
            r.recording_storage_path,
            r.duration_seconds  AS rec_duration,
            t.id               AS transcription_id,
            t.full_text         AS transcription_text
        FROM call_sessions cs
        LEFT JOIN ci_call_recordings r ON r.id = cs.recording_id
        LEFT JOIN ci_call_transcriptions t ON t.recording_id = r.id
        WHERE (
            CAST(cs.id AS TEXT) = :call_id
            OR CAST(cs.recording_id AS TEXT) = :call_id
            OR r.external_call_id = :call_id
        )
    """
    session_params: Dict[str, Any] = {"call_id": call_id}

    if org_id:
        session_sql += " AND cs.organization_id = :org_id"
        session_params["org_id"] = org_id

    session_sql += " LIMIT 1"

    try:
        row = db.execute(text(session_sql), session_params).fetchone()
    except Exception as e:
        logger.debug(f"call_sessions query failed (table may not exist): {e}")
        row = None

    if row:
        row_map = dict(row._mapping)
        session_id = str(row_map["session_id"])
        recording_url = row_map.get("recording_url") or row_map.get("recording_storage_path")
        transcript_text = row_map.get("transcription_text") or row_map.get("full_transcript")
        duration = row_map.get("rec_duration") or row_map.get("duration_seconds")
        transcription_id = row_map.get("transcription_id")

        # Fetch timed segments from ci_transcription_segments if available
        segments: Optional[List[TranscriptSegmentResponse]] = None
        if transcription_id:
            try:
                seg_rows = db.execute(text("""
                    SELECT speaker, speaker_label, text,
                           start_time_ms, end_time_ms, confidence
                    FROM ci_transcription_segments
                    WHERE transcription_id = :tid
                    ORDER BY segment_index
                """), {"tid": str(transcription_id)}).fetchall()

                if seg_rows:
                    segments = [
                        TranscriptSegmentResponse(
                            speaker=sr[0],
                            speaker_label=sr[1],
                            text=sr[2],
                            start_time_ms=sr[3],
                            end_time_ms=sr[4],
                            confidence=float(sr[5]) if sr[5] is not None else None,
                        )
                        for sr in seg_rows
                    ]
            except Exception as e:
                logger.debug(f"Segment query failed: {e}")

        # If no DB segments, try parsing timestamps from transcript text
        if not segments:
            parsed = _parse_transcript_segments_from_text(transcript_text)
            if parsed:
                segments = [TranscriptSegmentResponse(**s) for s in parsed]

        # Also try to pull agent_events transcript chunks as fallback segments
        if not segments:
            try:
                event_rows = db.execute(text("""
                    SELECT payload, transcript_timestamp_ms
                    FROM agent_events
                    WHERE session_id = :sid
                      AND event_type = 'transcript_chunk'
                    ORDER BY transcript_timestamp_ms NULLS LAST, event_time
                """), {"sid": session_id}).fetchall()

                if event_rows:
                    segments = []
                    for er in event_rows:
                        payload = er[0] if isinstance(er[0], dict) else {}
                        ts_ms = er[1] or payload.get("start_time_ms", 0)
                        segments.append(TranscriptSegmentResponse(
                            speaker=payload.get("speaker_label") or payload.get("speaker"),
                            speaker_label=payload.get("speaker_label"),
                            text=payload.get("text", ""),
                            start_time_ms=ts_ms,
                            end_time_ms=payload.get("end_time_ms", ts_ms + 5000),
                            confidence=payload.get("confidence"),
                        ))
            except Exception as e:
                logger.debug(f"agent_events segment fallback failed: {e}")

        # Fetch summary from scribe artifacts
        summary = None
        try:
            summary_row = db.execute(text("""
                SELECT content FROM call_artifacts
                WHERE session_id = :sid
                  AND artifact_type IN ('summary', 'scribe_recap')
                ORDER BY created_at DESC LIMIT 1
            """), {"sid": session_id}).fetchone()
            if summary_row:
                summary = summary_row[0]
        except Exception as e:
            logger.debug(f"Summary query failed: {e}")

        # Parse participants
        raw_participants = row_map.get("participants") or []
        participants = raw_participants if isinstance(raw_participants, list) else []

        return RecordingPlaybackResponse(
            call_id=session_id,
            source="call_session",
            recording_url=_maybe_presign_url(recording_url, org_id),
            duration_seconds=duration,
            transcript_text=transcript_text,
            transcript_segments=segments if segments else None,
            summary=summary,
            participants=participants,
            created_at=row_map["started_at"].isoformat() if row_map.get("started_at") else None,
        )

    # -----------------------------------------------------------------
    # 2. Try vapi_calls
    # -----------------------------------------------------------------
    vapi_row = db.execute(text("""
        SELECT vapi_call_id, recording_url, stereo_recording_url,
               transcript, summary, duration, lead_id, created_at
        FROM vapi_calls
        WHERE (vapi_call_id = :cid OR CAST(id AS TEXT) = :cid)
          AND (organization_id = :org_id OR organization_id IS NULL)
        LIMIT 1
    """), {"cid": call_id, "org_id": org_id}).fetchone()

    if vapi_row:
        transcript_text = vapi_row[3]
        segments = None
        parsed = _parse_transcript_segments_from_text(transcript_text)
        if parsed:
            segments = [TranscriptSegmentResponse(**s) for s in parsed]

        return RecordingPlaybackResponse(
            call_id=vapi_row[0],
            source="vapi",
            recording_url=_maybe_presign_url(vapi_row[1], org_id),
            stereo_recording_url=_maybe_presign_url(vapi_row[2], org_id),
            duration_seconds=vapi_row[5],
            transcript_text=transcript_text,
            transcript_segments=segments,
            summary=vapi_row[4],
            created_at=vapi_row[7].isoformat() if vapi_row[7] else None,
        )

    # -----------------------------------------------------------------
    # 3. Fallback: call_logs (dialer)
    # -----------------------------------------------------------------
    dialer_row = db.execute(text("""
        SELECT COALESCE(call_sid, CAST(id AS TEXT)),
               recording_url, stereo_recording_url,
               transcript_text, duration_seconds, lead_id, created_at
        FROM call_logs
        WHERE (call_sid = :cid OR CAST(id AS TEXT) = :cid)
          AND (organization_id = :org_id OR organization_id IS NULL)
        LIMIT 1
    """), {"cid": call_id, "org_id": org_id}).fetchone()

    if dialer_row:
        transcript_text = dialer_row[3]
        segments = None
        parsed = _parse_transcript_segments_from_text(transcript_text)
        if parsed:
            segments = [TranscriptSegmentResponse(**s) for s in parsed]

        return RecordingPlaybackResponse(
            call_id=dialer_row[0] or call_id,
            source="dialer",
            recording_url=_maybe_presign_url(dialer_row[1], org_id),
            stereo_recording_url=_maybe_presign_url(dialer_row[2], org_id),
            duration_seconds=dialer_row[4],
            transcript_text=transcript_text,
            transcript_segments=segments,
            created_at=dialer_row[6].isoformat() if dialer_row[6] else None,
        )

    raise HTTPException(status_code=404, detail="Call recording not found")


# =============================================================================
# MOBILE AUDIO STREAMING WEBSOCKET
# =============================================================================

@router.websocket("/sessions/{session_id}/audio-stream")
async def stream_audio_to_transcript(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for mobile call intelligence.

    Accepts PCM16 audio chunks from the mobile app, streams them to Deepgram
    for real-time transcription, and feeds transcript text into the existing
    call monitoring session pipeline (6 AI agents).

    Client sends:  {"type": "audio", "data": "<base64-pcm16-audio>"}
    Server sends:  {"type": "transcript", "text": "...", "is_final": true/false}
                   {"type": "error", "message": "..."}
                   {"type": "connected", "session_id": "..."}
    """
    from database import SessionLocal
    from utils.websocket_auth import authenticate_websocket

    await websocket.accept()

    deepgram_ws = None
    db = None
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "")

    try:
        # Authenticate
        db = SessionLocal()
        user, auth_error = authenticate_websocket(websocket, db, require_auth=True)

        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Auth failed"})
            await websocket.close()
            return

        await websocket.send_json({"type": "connected", "session_id": session_id})
        logger.info(f"[AudioStream] Mobile audio stream connected for session {session_id}")

        if not deepgram_api_key:
            await websocket.send_json({"type": "error", "message": "Transcription service not configured"})
            await websocket.close()
            return

        # Connect to Deepgram streaming API
        import websockets

        dg_url = (
            "wss://api.deepgram.com/v1/listen?"
            "encoding=linear16&sample_rate=16000&channels=1&model=nova-2"
            "&language=en-US&smart_format=true&punctuate=true"
            "&interim_results=true&endpointing=300&vad_events=true"
        )
        dg_headers = {"Authorization": f"Token {deepgram_api_key}"}
        deepgram_ws = await websockets.connect(dg_url, extra_headers=dg_headers)
        logger.info(f"[AudioStream] Deepgram connected for session {session_id}")

        # Task to listen for Deepgram responses and forward to client + backend
        async def listen_deepgram():
            try:
                async for message in deepgram_ws:
                    data = json.loads(message)
                    if data.get("type") == "Results":
                        alternatives = data.get("channel", {}).get("alternatives", [])
                        if alternatives:
                            text = alternatives[0].get("transcript", "")
                            confidence = alternatives[0].get("confidence", 0)
                            is_final = data.get("is_final", False)

                            if text:
                                # Send transcript to mobile client
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": text,
                                    "is_final": is_final,
                                    "confidence": confidence,
                                })

                                # Feed final transcripts into the session pipeline
                                if is_final:
                                    try:
                                        orchestrator = CallMonitoringOrchestrator(db)
                                        await orchestrator.process_transcript_chunk(
                                            session_id=session_id,
                                            chunk=text,
                                            speaker=None,
                                            timestamp_ms=None,
                                        )
                                    except Exception as e:
                                        logger.error(f"[AudioStream] Error processing chunk: {e}")

            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[AudioStream] Deepgram connection closed for session {session_id}")
            except Exception as e:
                logger.error(f"[AudioStream] Deepgram listener error: {e}")

        # Start Deepgram listener in background
        dg_task = asyncio.create_task(listen_deepgram())

        # Main loop: receive audio from mobile client, forward to Deepgram
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)

                if msg.get("type") == "audio" and msg.get("data"):
                    audio_bytes = base64.b64decode(msg["data"])
                    await deepgram_ws.send(audio_bytes)

                elif msg.get("type") == "stop":
                    logger.info(f"[AudioStream] Client requested stop for session {session_id}")
                    break

        except WebSocketDisconnect:
            logger.info(f"[AudioStream] Mobile client disconnected for session {session_id}")
        finally:
            dg_task.cancel()

    except Exception as e:
        logger.error(f"[AudioStream] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "Audio stream error"})
        except Exception as e:
            logger.error(f"Error sending error message to websocket: {e}")
    finally:
        if deepgram_ws:
            try:
                await deepgram_ws.close()
            except Exception as e:
                logger.error(f"Error closing deepgram websocket: {e}")
        if db:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing db session: {e}")
        try:
            await websocket.close()
        except Exception as e:
            logger.error(f"Error closing websocket: {e}")
        logger.info(f"[AudioStream] Session {session_id} audio stream closed")


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
    """Background task to run agents, then trigger post-call automation and CI extraction."""
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

            # -----------------------------------------------------------
            # Post-agent pipeline: CI extraction → orchestration → post-call automation
            # Failures here MUST NOT break the existing agent pipeline.
            # -----------------------------------------------------------
            await _run_post_agent_pipeline(db, session_id, user_id)

        finally:
            db.close()

    except SQLAlchemyError as e:
        logger.error(f"Background agent processing failed: {e}")


# Minimum transcript length (in characters) to justify running CI extraction.
# Short transcripts (greetings-only, missed calls) produce low-value extractions.
_MIN_TRANSCRIPT_LEN_FOR_CI = 200


async def _run_post_agent_pipeline(
    db: Session,
    session_id: str,
    user_id: Optional[int] = None,
) -> None:
    """
    Run post-call automation and CI extraction after the call monitoring agents finish.

    Sequence:
      1. Fetch session context (transcript, loan_id, org_id, metadata).
      2. CI extraction (6 domain agents) — produces extracted_data for the orchestrator.
      3. CI orchestration (lead creation, pre-qual, doc checklist, outreach, scheduling).
      4. Post-call automation (summary, action items, compliance score, follow-up SMS).

    Every step is wrapped in its own try/except so a failure in one does not block the others.
    """
    # -- Fetch session context ------------------------------------------------
    try:
        session_row = db.execute(text("""
            SELECT id, full_transcript, loan_id, lead_id, user_id,
                   organization_id, metadata, duration_seconds, status,
                   capture_mode
            FROM call_sessions
            WHERE id = :sid
        """), {"sid": session_id}).fetchone()
    except Exception as e:
        logger.error(f"[PostAgentPipeline] Failed to fetch session {session_id}: {e}")
        return

    if not session_row:
        logger.warning(f"[PostAgentPipeline] Session {session_id} not found — skipping post-agent pipeline")
        return

    transcript = session_row[1] or ""
    loan_id_raw = session_row[2]          # UUID or None
    lead_id_raw = session_row[3]          # UUID or None
    session_user_id = session_row[4]      # UUID or None
    org_id = session_row[5]               # int or None
    session_metadata = session_row[6] or {}
    duration_seconds = session_row[7]
    capture_mode = session_row[9]

    if not transcript or len(transcript.strip()) < _MIN_TRANSCRIPT_LEN_FOR_CI:
        logger.info(
            f"[PostAgentPipeline] Transcript too short ({len(transcript)} chars) for session "
            f"{session_id} — skipping CI extraction and post-call automation"
        )
        return

    # Convert UUID loan_id to int if it looks like an integer (CRM loans use integer PKs).
    # If the UUID is a true UUID string we pass it as-is where accepted.
    loan_id_str = str(loan_id_raw) if loan_id_raw else None
    loan_id_int: Optional[int] = None
    if loan_id_str:
        try:
            loan_id_int = int(loan_id_str)
        except (ValueError, TypeError):
            # True UUID — some downstream services accept str, others need int.
            pass

    org_id_int: Optional[int] = None
    if org_id is not None:
        try:
            org_id_int = int(org_id)
        except (ValueError, TypeError):
            pass

    call_id = str(session_id)
    lo_user_id = user_id or (int(str(session_user_id)) if session_user_id else None)

    # -- Step 1: CI Extraction ------------------------------------------------
    ci_result: Optional[Dict[str, Any]] = None
    try:
        from services.call_intelligence.integration import CallIntelligenceIntegration

        ci_integration = CallIntelligenceIntegration(db_session=db)
        ci_result = await ci_integration.process_completed_call(
            call_id=call_id,
            loan_id=loan_id_int,
            organization_id=org_id_int or 0,
            transcript=transcript,
            call_type="call_monitoring",
            call_metadata={
                "source": "call_monitoring_agents",
                "session_id": session_id,
                "capture_mode": capture_mode,
                "duration_seconds": duration_seconds,
                "user_id": lo_user_id,
            },
        )
        if ci_result and ci_result.get("success"):
            logger.info(
                f"[PostAgentPipeline] CI extraction succeeded for session {session_id}: "
                f"extractions={ci_result.get('extractions_count', 0)}, "
                f"high_confidence={ci_result.get('high_confidence_count', 0)}"
            )
        else:
            logger.warning(
                f"[PostAgentPipeline] CI extraction returned non-success for session {session_id}: "
                f"{ci_result}"
            )
    except Exception as e:
        logger.error(f"[PostAgentPipeline] CI extraction failed for session {session_id}: {e}", exc_info=True)

    # -- Step 2: CI Orchestration (lead creation, pre-qual, docs, outreach, scheduling) --
    try:
        from services.call_intelligence.orchestration.orchestrator import (
            CallIntelligenceOrchestrator,
            OrchestrationConfig,
        )

        # Build extracted_data dict from CI result or fall back to empty structure.
        extracted_data: Dict[str, Any] = {}
        if ci_result and ci_result.get("success"):
            # The CI processor saves full extraction results in the DB; the
            # orchestrator only needs the high-level dict.  Re-use what we can
            # from the ci_result; the orchestrator's _normalize_extracted_data
            # will handle missing keys gracefully.
            extracted_data = ci_result

        orch_config = OrchestrationConfig(
            continue_on_step_failure=True,
        )
        ci_orchestrator = CallIntelligenceOrchestrator(config=orch_config)
        orch_result = await ci_orchestrator.orchestrate(
            call_id=call_id,
            extracted_data=extracted_data,
            loan_id=loan_id_int,
            organization_id=org_id_int,
            assigned_to=str(lo_user_id) if lo_user_id else None,
        )
        logger.info(
            f"[PostAgentPipeline] CI orchestration completed for session {session_id}: "
            f"status={orch_result.status.value}, "
            f"successful_steps={orch_result.successful_steps}/{orch_result.successful_steps + orch_result.failed_steps}"
        )
    except Exception as e:
        logger.error(f"[PostAgentPipeline] CI orchestration failed for session {session_id}: {e}", exc_info=True)

    # -- Step 3: Post-Call Automation (summary, action items, compliance, SMS) --
    try:
        from services.call_intelligence.post_call_automation import PostCallAutomationService

        if org_id_int is None:
            logger.warning(
                f"[PostAgentPipeline] Skipping post-call automation for session {session_id}: "
                f"no organization_id on session"
            )
        elif loan_id_int is None:
            logger.info(
                f"[PostAgentPipeline] Skipping post-call automation for session {session_id}: "
                f"no integer loan_id (loan_id_raw={loan_id_raw})"
            )
        else:
            # Build call_metadata expected by PostCallAutomationService
            call_metadata: Dict[str, Any] = {
                "lo_user_id": lo_user_id,
                "borrower_name": (session_metadata or {}).get("borrower_name", ""),
                "borrower_phone": (session_metadata or {}).get("borrower_phone", ""),
                "call_duration_seconds": duration_seconds or 0,
                "call_direction": (session_metadata or {}).get("call_direction", "unknown"),
                "call_outcome": (session_metadata or {}).get("call_outcome", ""),
                "lead_id": int(str(lead_id_raw)) if lead_id_raw else None,
            }

            post_call_svc = PostCallAutomationService(db)
            post_call_results = await post_call_svc.process_call_end(
                call_id=call_id,
                loan_id=loan_id_int,
                org_id=org_id_int,
                transcript=transcript,
                call_metadata=call_metadata,
            )
            logger.info(
                f"[PostAgentPipeline] Post-call automation completed for session {session_id}: "
                f"summary_len={len(post_call_results.get('summary') or '')}, "
                f"action_items={len(post_call_results.get('action_items') or [])}, "
                f"compliance_score={post_call_results.get('compliance_score', 0)}"
            )
    except Exception as e:
        logger.error(
            f"[PostAgentPipeline] Post-call automation failed for session {session_id}: {e}",
            exc_info=True,
        )
