"""
Mobile Call Intelligence Routes

Bridge between the mobile frontend's /api/call-intelligence/* API contract
(callIntelligenceApi.js) and the existing call_monitoring infrastructure.

Endpoints:
  POST /api/call-intelligence/start          — Start a CI session
  POST /api/call-intelligence/{id}/end       — End call, trigger agents
  GET  /api/call-intelligence/active         — Active session for an LO
  GET  /api/call-intelligence/history        — Call history for an LO
  GET  /api/call-intelligence/{id}/summary   — Post-call summary
  POST /api/call-intelligence/{id}/doc-requests/{rid}/approve
  PATCH /api/call-intelligence/{id}/flags/{fid}
  POST /api/call-intelligence/{id}/application
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models.call_monitoring_models import CaptureMode
from services.call_monitoring import CallMonitoringOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/call-intelligence", tags=["Mobile Call Intelligence"])


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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# =============================================================================
# E.164 PHONE VALIDATION
# =============================================================================

_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")
_US_DIGITS_PATTERN = re.compile(r"^\d{10}$")


def _normalize_phone(raw: str) -> str:
    """
    Normalize a phone string to E.164 format.

    Accepts:
      +18005551234         -> +18005551234
      8005551234           -> +18005551234
      (800) 555-1234       -> +18005551234
      1-800-555-1234       -> +18005551234

    Raises ValueError for unparseable input.
    """
    stripped = re.sub(r"[\s()\-.]", "", raw)

    if _E164_PATTERN.match(stripped):
        return stripped

    digits = re.sub(r"\D", "", stripped)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"

    raise ValueError("Invalid phone number format")


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class StartCallRequest(BaseModel):
    """Request to start a call intelligence session."""
    borrower_phone: str = Field(..., min_length=1, max_length=30)
    borrower_name: Optional[str] = Field(None, max_length=200)
    borrower_email: Optional[str] = Field(None, max_length=255)
    appointment_type: Optional[str] = Field(None, max_length=100)
    lo_user_id: Optional[str] = Field(None, max_length=100)
    lead_id: Optional[str] = Field(None, max_length=100)
    loan_id: Optional[str] = Field(None, max_length=100)

    @field_validator("borrower_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return _normalize_phone(v)
        except ValueError:
            raise ValueError(
                "borrower_phone must be a valid phone number "
                "(E.164 or 10-digit US)"
            )


class EndCallRequest(BaseModel):
    """Optional body when ending a call."""
    final_transcript: Optional[str] = None
    run_agents: bool = True


class DismissFlagRequest(BaseModel):
    """Request to dismiss an audit flag."""
    resolved: bool


class ApplicationDraftRequest(BaseModel):
    """Request to save loan application fields."""
    fields: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# SERIALIZATION HELPERS
# =============================================================================

def _serialize_row(row_mapping: dict) -> dict:
    """Convert a SQLAlchemy row mapping to JSON-safe dict."""
    out = {}
    for key, val in row_mapping.items():
        if isinstance(val, UUID):
            out[key] = str(val)
        elif isinstance(val, datetime):
            out[key] = val.isoformat()
        else:
            out[key] = val
    return out


# =============================================================================
# BACKGROUND TASK: RUN AGENTS
# =============================================================================

async def _run_agents_background(
    db_url: str,
    session_id: str,
    user_id: Optional[str] = None,
):
    """
    Background task to run all CI agents on a session.

    Creates its own DB session to avoid lifetime issues with the request
    session, then delegates to the existing orchestrator + post-agent pipeline.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    try:
        engine = create_engine(db_url)
        _SessionLocal = sessionmaker(bind=engine)
        db = _SessionLocal()

        # Set RLS tenant context if we know the user
        if user_id:
            try:
                org_row = db.execute(
                    text("SELECT organization_id FROM users WHERE id = :uid"),
                    {"uid": user_id},
                ).fetchone()
                if org_row and org_row[0]:
                    try:
                        from database.tenant_mixin import set_tenant_context
                        set_tenant_context(db, org_row[0])
                    except ImportError:
                        pass
            except Exception:
                pass

        try:
            orchestrator = CallMonitoringOrchestrator(db)
            await orchestrator.run_agents(
                session_id=session_id,
                agent_types=None,  # all agents
                trigger="call_intelligence_end",
            )

            # Run post-agent pipeline (CI extraction, orchestration, post-call automation)
            try:
                from routes.call_monitoring_routes import _run_post_agent_pipeline
                await _run_post_agent_pipeline(db, session_id, user_id)
            except ImportError:
                logger.debug("Post-agent pipeline not available; skipping")
            except Exception as e:
                logger.warning(f"Post-agent pipeline failed for session {session_id}: {e}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Background agent processing failed for session {session_id}: {e}")


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/start", response_model=Dict[str, Any])
async def start_call(
    request: StartCallRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Start a call intelligence session.

    Creates a CallSession with capture_mode=call_intelligence, adds the
    borrower and LO as participants, and returns the session handle.
    """
    try:
        user_id = str(current_user.get("id", ""))
        org_id = current_user.get("organization_id")
        lo_user_id = request.lo_user_id or user_id

        orchestrator = CallMonitoringOrchestrator(db, organization_id=org_id)

        # Create session
        result = orchestrator.create_session(
            capture_mode=CaptureMode.CALL_INTELLIGENCE.value,
            user_id=lo_user_id,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            metadata={
                "appointment_type": request.appointment_type,
                "borrower_phone": request.borrower_phone,
                "borrower_email": request.borrower_email,
                "source": "mobile_call_intelligence",
            },
        )

        session_id = result["session_id"]

        # Add LO as participant
        await orchestrator.add_participant(
            session_id=session_id,
            role="loan_officer",
            user_id=lo_user_id,
            name=current_user.get("name") or current_user.get("email", ""),
            email=current_user.get("email"),
        )

        # Add borrower as participant
        await orchestrator.add_participant(
            session_id=session_id,
            role="borrower",
            phone=request.borrower_phone,
            name=request.borrower_name,
            email=request.borrower_email,
        )

        return {
            "session_id": session_id,
            "status": "active",
            "created_at": result["started_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start call intelligence session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start session",
        )


@router.post("/{session_id}/end", response_model=Dict[str, Any])
async def end_call(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: Optional[EndCallRequest] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    End a call intelligence session and trigger AI agent processing.

    Marks the session as 'processing' and queues all agents (scribe,
    junior_lo, underwriter) to run in the background.
    """
    try:
        org_id = current_user.get("organization_id")
        orchestrator = CallMonitoringOrchestrator(db, organization_id=org_id)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        now = datetime.now(timezone.utc)

        # Set final transcript if provided
        if body and body.final_transcript:
            orchestrator.set_transcript(session_id, body.final_transcript)

        # Transition to processing
        orchestrator.update_session(session_id, status="processing", ended_at=now)

        # Queue agent processing
        run_agents = body.run_agents if body else True
        if run_agents:
            try:
                db_url = str(db.get_bind().url)
            except Exception:
                db_url = None

            if db_url:
                background_tasks.add_task(
                    _run_agents_background,
                    db_url=db_url,
                    session_id=session_id,
                    user_id=str(current_user.get("id", "")),
                )

        return {
            "session_id": session_id,
            "status": "processing",
            "ended_at": now.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end session",
        )


@router.get("/active", response_model=Optional[Dict[str, Any]])
async def get_active_session(
    lo_user_id: str = Query(..., description="Loan officer user ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the currently active call intelligence session for an LO.

    Returns null if no active session exists.
    """
    try:
        org_id = current_user.get("organization_id")

        query = """
            SELECT id, capture_mode, status, loan_id, lead_id, contact_id,
                   user_id, participants, metadata, started_at, created_at
            FROM call_sessions
            WHERE user_id = :lo_user_id
              AND status = 'active'
        """
        params: Dict[str, Any] = {"lo_user_id": lo_user_id}

        if org_id:
            query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        query += " ORDER BY created_at DESC LIMIT 1"

        row = db.execute(text(query), params).fetchone()

        if not row:
            return None

        row_dict = dict(row._mapping)
        return _serialize_row(row_dict)

    except Exception as e:
        logger.error(f"Failed to get active session for LO {lo_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get active session",
        )


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_call_history(
    lo_user_id: str = Query(..., description="Loan officer user ID"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get call history for an LO.

    Returns completed and processing sessions, most recent first.
    """
    try:
        org_id = current_user.get("organization_id")

        query = """
            SELECT cs.id, cs.capture_mode, cs.status, cs.loan_id, cs.lead_id,
                   cs.contact_id, cs.user_id, cs.participants, cs.metadata,
                   cs.started_at, cs.ended_at, cs.duration_seconds,
                   cs.created_at,
                   (SELECT COUNT(*)
                    FROM call_artifacts ca
                    WHERE ca.session_id = cs.id) AS artifact_count
            FROM call_sessions cs
            WHERE cs.user_id = :lo_user_id
              AND cs.status IN ('completed', 'processing', 'review_pending')
        """
        params: Dict[str, Any] = {"lo_user_id": lo_user_id, "limit": limit}

        if org_id:
            query += " AND cs.organization_id = :org_id"
            params["org_id"] = org_id

        query += " ORDER BY cs.created_at DESC LIMIT :limit"

        result = db.execute(text(query), params)
        sessions = []
        for row in result:
            sessions.append(_serialize_row(dict(row._mapping)))

        return sessions

    except Exception as e:
        logger.error(f"Failed to get call history for LO {lo_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get call history",
        )


@router.get("/{session_id}/summary", response_model=Dict[str, Any])
async def get_call_summary(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the full post-call summary for a session.

    Aggregates artifacts by type and returns a structured response
    suitable for the mobile review screen.
    """
    try:
        org_id = current_user.get("organization_id")
        orchestrator = CallMonitoringOrchestrator(db, organization_id=org_id)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Fetch all artifacts for the session
        artifact_query = """
            SELECT id, artifact_type, title, content, structured_data,
                   approval_status, execution_status, confidence,
                   source_evidence, priority, created_at
            FROM call_artifacts
            WHERE session_id = :session_id
        """
        artifact_params: Dict[str, Any] = {"session_id": session_id}

        if org_id:
            artifact_query += " AND organization_id = :org_id"
            artifact_params["org_id"] = org_id

        artifact_query += " ORDER BY created_at ASC"

        rows = db.execute(text(artifact_query), artifact_params)
        artifacts = [_serialize_row(dict(r._mapping)) for r in rows]

        # Group artifacts by type
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for artifact in artifacts:
            atype = artifact.get("artifact_type", "other")
            grouped.setdefault(atype, []).append(artifact)

        # Fetch risk flags
        flag_query = """
            SELECT id, risk_category, severity, title, description,
                   evidence, recommended_action, status, condition_type,
                   created_at
            FROM call_risk_flags
            WHERE session_id = :session_id
        """
        flag_params: Dict[str, Any] = {"session_id": session_id}

        if org_id:
            flag_query += " AND organization_id = :org_id"
            flag_params["org_id"] = org_id

        flag_query += " ORDER BY CASE severity "
        flag_query += "WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
        flag_query += "WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC"

        flag_rows = db.execute(text(flag_query), flag_params)
        risk_flags = [_serialize_row(dict(r._mapping)) for r in flag_rows]

        # Fetch intake field updates
        intake_query = """
            SELECT id, entity_type, entity_id, field_name, field_path,
                   current_value, proposed_value, confidence,
                   has_conflict, status, created_at
            FROM intake_field_updates
            WHERE session_id = :session_id
        """
        intake_params: Dict[str, Any] = {"session_id": session_id}

        if org_id:
            intake_query += " AND organization_id = :org_id"
            intake_params["org_id"] = org_id

        intake_query += " ORDER BY created_at ASC"

        intake_rows = db.execute(text(intake_query), intake_params)
        intake_fields = [_serialize_row(dict(r._mapping)) for r in intake_rows]

        # Build summary
        summary_artifacts = grouped.get("summary", []) + grouped.get("scribe_recap", [])
        summary_text = None
        if summary_artifacts:
            summary_text = summary_artifacts[0].get("content")

        return {
            "session_id": session_id,
            "status": session.get("status"),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "duration_seconds": session.get("duration_seconds"),
            "participants": session.get("participants", []),
            "summary": summary_text,
            "artifacts": artifacts,
            "artifacts_by_type": grouped,
            "risk_flags": risk_flags,
            "intake_fields": intake_fields,
            "counts": {
                "total_artifacts": len(artifacts),
                "action_items": len(grouped.get("action_item", [])),
                "tasks": len(grouped.get("task", [])),
                "document_requests": len(grouped.get("document_request", [])),
                "risk_flags": len(risk_flags),
                "intake_fields": len(intake_fields),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get summary for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get call summary",
        )


@router.post(
    "/{session_id}/doc-requests/{request_id}/approve",
    response_model=Dict[str, Any],
)
async def approve_doc_request(
    session_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Approve a document request artifact.

    Delegates to the orchestrator's approve_artifacts method for
    the single artifact identified by request_id.
    """
    try:
        org_id = current_user.get("organization_id")
        user_id = str(current_user.get("id", ""))
        orchestrator = CallMonitoringOrchestrator(db, organization_id=org_id)

        session = orchestrator.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify the artifact exists and belongs to this session
        verify_query = """
            SELECT id FROM call_artifacts
            WHERE id = :artifact_id AND session_id = :session_id
        """
        verify_params: Dict[str, Any] = {
            "artifact_id": request_id,
            "session_id": session_id,
        }
        if org_id:
            verify_query += " AND organization_id = :org_id"
            verify_params["org_id"] = org_id

        artifact_row = db.execute(text(verify_query), verify_params).fetchone()
        if not artifact_row:
            raise HTTPException(
                status_code=404, detail="Document request not found"
            )

        result = await orchestrator.approve_artifacts(
            session_id=session_id,
            artifact_ids=[request_id],
            user_id=user_id,
            action="approve",
        )

        return {
            "status": "success",
            "session_id": session_id,
            "request_id": request_id,
            "approved": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to approve doc request {request_id} "
            f"for session {session_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve document request",
        )


@router.patch(
    "/{session_id}/flags/{flag_id}",
    response_model=Dict[str, Any],
)
async def dismiss_flag(
    session_id: str,
    flag_id: str,
    body: DismissFlagRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Dismiss (resolve) an audit flag.

    Updates the call_risk_flags row to 'resolved' or 'open' based on
    the resolved field in the request body.
    """
    try:
        org_id = current_user.get("organization_id")
        user_id = str(current_user.get("id", ""))
        now = datetime.now(timezone.utc)

        new_status = "resolved" if body.resolved else "open"

        update_query = """
            UPDATE call_risk_flags
            SET status = :new_status,
                resolved_by = :user_id,
                resolved_at = :now,
                updated_at = :now
            WHERE id = :flag_id AND session_id = :session_id
        """
        params: Dict[str, Any] = {
            "new_status": new_status,
            "user_id": user_id,
            "now": now,
            "flag_id": flag_id,
            "session_id": session_id,
        }

        if org_id:
            update_query += " AND organization_id = :org_id"
            params["org_id"] = org_id

        result = db.execute(text(update_query), params)
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Flag not found")

        return {
            "status": "success",
            "session_id": session_id,
            "flag_id": flag_id,
            "resolved": body.resolved,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update flag {flag_id} for session {session_id}: {e}"
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update flag",
        )


@router.post("/{session_id}/application", response_model=Dict[str, Any])
async def save_application_draft(
    session_id: str,
    body: ApplicationDraftRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Save loan application field values extracted during the call.

    Looks up the loan associated with the session (or creates via the
    linked lead_id) and updates the loan record with the provided fields.
    """
    try:
        org_id = current_user.get("organization_id")
        orchestrator = CallMonitoringOrchestrator(db, organization_id=org_id)
        session = orchestrator.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        fields = body.fields
        if not fields:
            return {
                "success": True,
                "session_id": session_id,
                "fields_updated": 0,
            }

        loan_id = session.get("loan_id")
        lead_id = session.get("lead_id")

        if not loan_id and not lead_id:
            raise HTTPException(
                status_code=400,
                detail="Session has no linked loan or lead",
            )

        # Allowlisted loan columns that the mobile client may update.
        # This prevents arbitrary column injection.
        _ALLOWED_LOAN_FIELDS = {
            "borrower_first_name", "borrower_last_name",
            "borrower_email", "borrower_phone",
            "co_borrower_first_name", "co_borrower_last_name",
            "co_borrower_email", "co_borrower_phone",
            "loan_purpose", "loan_amount", "property_type",
            "property_address", "property_city", "property_state",
            "property_zip", "estimated_value", "purchase_price",
            "down_payment", "down_payment_percent",
            "annual_income", "monthly_income",
            "credit_score", "employment_status", "employer_name",
            "years_employed", "monthly_debt",
            "notes",
        }

        _ALLOWED_LEAD_FIELDS = {
            "first_name", "last_name", "email", "phone",
            "loan_purpose", "loan_amount", "property_type",
            "property_address", "credit_score",
            "annual_income", "notes",
        }

        fields_updated = 0

        if loan_id:
            # Update loan record
            safe_fields = {
                k: v for k, v in fields.items() if k in _ALLOWED_LOAN_FIELDS
            }
            if safe_fields:
                set_clauses = []
                params: Dict[str, Any] = {"loan_id": loan_id}
                for idx, (col, val) in enumerate(safe_fields.items()):
                    param_name = f"v{idx}"
                    set_clauses.append(f"{col} = :{param_name}")
                    params[param_name] = val

                set_clauses.append("updated_at = NOW()")
                update_sql = (
                    f"UPDATE loans SET {', '.join(set_clauses)} "
                    f"WHERE id = :loan_id"
                )
                if org_id:
                    update_sql += " AND organization_id = :org_id"
                    params["org_id"] = org_id

                db.execute(text(update_sql), params)
                db.commit()
                fields_updated = len(safe_fields)

        elif lead_id:
            # Update lead record
            safe_fields = {
                k: v for k, v in fields.items() if k in _ALLOWED_LEAD_FIELDS
            }
            if safe_fields:
                set_clauses = []
                params = {"lead_id": lead_id}
                for idx, (col, val) in enumerate(safe_fields.items()):
                    param_name = f"v{idx}"
                    set_clauses.append(f"{col} = :{param_name}")
                    params[param_name] = val

                set_clauses.append("updated_at = NOW()")
                update_sql = (
                    f"UPDATE leads SET {', '.join(set_clauses)} "
                    f"WHERE id = :lead_id"
                )
                if org_id:
                    update_sql += " AND organization_id = :org_id"
                    params["org_id"] = org_id

                db.execute(text(update_sql), params)
                db.commit()
                fields_updated = len(safe_fields)

        return {
            "success": True,
            "session_id": session_id,
            "fields_updated": fields_updated,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to save application draft for session {session_id}: {e}"
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save application draft",
        )
