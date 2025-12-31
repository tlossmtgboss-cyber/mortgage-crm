"""
Intake Engine API Routes
FastAPI router for intake session management
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from datetime import datetime

from ..runtime import (
    IntakeEngine,
    create_engine,
    Session,
    PartyType,
    SessionStatus,
)

router = APIRouter(prefix="/api/v1/intake", tags=["intake"])


@router.post("/admin/create-tables")
async def create_intake_tables(admin_key: str = None):
    """Create intake engine database tables"""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=401, detail="Invalid admin key")

    import os
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)

    results = []
    with Session() as db:
        try:
            # Create intake_sessions table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS intake_sessions (
                    session_id VARCHAR(50) PRIMARY KEY,
                    data JSONB NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            results.append("intake_sessions table created")

            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intake_sessions_expires
                ON intake_sessions(expires_at)
            """))

            # Create intake_audit_events table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS intake_audit_events (
                    event_id VARCHAR(50) PRIMARY KEY,
                    session_id VARCHAR(50) NOT NULL,
                    party_id VARCHAR(50),
                    event_type VARCHAR(50) NOT NULL,
                    payload JSONB,
                    hash_prev VARCHAR(64),
                    hash_self VARCHAR(64),
                    pii_redacted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            results.append("intake_audit_events table created")

            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intake_audit_session
                ON intake_audit_events(session_id)
            """))

            # Create intake_sla_tasks table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS intake_sla_tasks (
                    task_id VARCHAR(50) PRIMARY KEY,
                    session_id VARCHAR(50) NOT NULL,
                    loan_id VARCHAR(50),
                    task_type VARCHAR(100) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    priority VARCHAR(20) DEFAULT 'medium',
                    due_in_minutes INTEGER,
                    assignee_role VARCHAR(100),
                    trigger_flags TEXT[],
                    score_band VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """))
            results.append("intake_sla_tasks table created")

            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intake_sla_session
                ON intake_sla_tasks(session_id)
            """))

            db.commit()
            return {"status": "success", "results": results}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

# Engine instance (singleton)
_engine: Optional[IntakeEngine] = None


def get_engine() -> IntakeEngine:
    """Get or create engine instance"""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    loan_id: Optional[str] = None
    borrower_id: Optional[str] = None
    mode: str = "intake_prequal"
    locale: str = "en-US"


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    current_section: str
    created_at: str


class NextQuestionResponse(BaseModel):
    question_id: str
    prompt: str
    answer_types: List[str]
    ui: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[List[Dict[str, Any]]] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class SubmitAnswerRequest(BaseModel):
    question_id: str
    value: Any
    party_id: Optional[str] = None
    response_time_ms: int = 0
    device_rtt_ms: int = 0
    edits_in_window: int = 0


class SubmitAnswerResponse(BaseModel):
    accepted: bool
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    flags_added: List[str] = Field(default_factory=list)
    scores: Dict[str, Any] = Field(default_factory=dict)
    next: Optional[NextQuestionResponse] = None
    overlay: Optional[Dict[str, Any]] = None


class AddPartyRequest(BaseModel):
    party_type: str  # PRIMARY, CO_BORROWER, NON_BORROWING_SPOUSE
    display_name: Optional[str] = None


class AddPartyResponse(BaseModel):
    party_id: str
    party_type: str
    display_name: Optional[str]


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    current_section: str
    parties: List[Dict[str, Any]]
    scores: Dict[str, Any]
    flags: List[Dict[str, Any]]
    progress: Dict[str, Any]


class CompleteSessionResponse(BaseModel):
    status: str
    urla_payload: Dict[str, Any]
    scores: Dict[str, Any]
    flags: List[Dict[str, Any]]
    sla_tasks_created: List[Dict[str, Any]]
    redirect: Optional[str] = None


class CaptureConsentRequest(BaseModel):
    consent_key: str
    accepted: bool
    version_hash: str


class AuditTrailResponse(BaseModel):
    session_id: str
    events: List[Dict[str, Any]]
    chain_valid: bool


# =============================================================================
# Session Management Endpoints
# =============================================================================

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    engine: IntakeEngine = Depends(get_engine),
):
    """Create a new intake session"""
    try:
        session = engine.create_session(
            loan_id=request.loan_id,
            borrower_id=request.borrower_id,
            mode=request.mode,
            locale=request.locale,
        )

        return CreateSessionResponse(
            session_id=session.session_id,
            status=session.status.value if hasattr(session.status, 'value') else str(session.status),
            current_section=session.current_section,
            created_at=session.created_at.isoformat(),
        )
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Session creation failed: {str(e)}\n{traceback.format_exc()}")


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get current session status and progress"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Calculate progress
    answered = len(session.answers) + sum(len(pa) for pa in session.party_answers.values())
    total = len(engine.questions)

    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        current_section=session.current_section,
        parties=[
            {
                "party_id": p.party_id,
                "party_type": p.party_type,
                "display_name": p.display_name,
                "is_complete": p.is_complete,
            }
            for p in session.parties
        ],
        scores={
            "truth_score": session.scores.underwriting_truth_score,
            "truth_band": session.scores.truth_band,
            "readiness_score": session.scores.lo_readiness_score,
            "hesitation_score": session.scores.hesitation_score,
            "hesitation_band": session.scores.hesitation_band,
        },
        flags=[
            {
                "code": f.code,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
            }
            for f in session.flags
        ],
        progress={
            "answered": answered,
            "total": total,
            "percentage": round((answered / total) * 100, 1) if total > 0 else 0,
        },
    )


@router.post("/sessions/{session_id}/resume", response_model=SessionStatusResponse)
async def resume_session(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Resume a paused session"""
    session = engine.resume_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return same format as get_session_status
    answered = len(session.answers) + sum(len(pa) for pa in session.party_answers.values())
    total = len(engine.questions)

    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        current_section=session.current_section,
        parties=[
            {
                "party_id": p.party_id,
                "party_type": p.party_type,
                "display_name": p.display_name,
                "is_complete": p.is_complete,
            }
            for p in session.parties
        ],
        scores={
            "truth_score": session.scores.underwriting_truth_score,
            "truth_band": session.scores.truth_band,
            "readiness_score": session.scores.lo_readiness_score,
            "hesitation_score": session.scores.hesitation_score,
            "hesitation_band": session.scores.hesitation_band,
        },
        flags=[
            {
                "code": f.code,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
            }
            for f in session.flags
        ],
        progress={
            "answered": answered,
            "total": total,
            "percentage": round((answered / total) * 100, 1) if total > 0 else 0,
        },
    )


# =============================================================================
# Question Flow Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/next", response_model=Optional[NextQuestionResponse])
async def get_next_question(
    session_id: str,
    party_id: Optional[str] = None,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get the next question to ask"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Session is {session.status}")

    next_q = engine.get_next_question(session, party_id)
    if not next_q:
        return None

    return NextQuestionResponse(
        question_id=next_q.question_id,
        prompt=next_q.prompt,
        answer_types=next_q.answer_types,
        ui=next_q.ui,
        options=next_q.options,
        context=next_q.context,
    )


@router.post("/sessions/{session_id}/answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    session_id: str,
    request: SubmitAnswerRequest,
    engine: IntakeEngine = Depends(get_engine),
):
    """Submit an answer to a question"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Session is {session.status}")

    result = engine.submit_answer(
        session=session,
        question_id=request.question_id,
        value=request.value,
        party_id=request.party_id,
        response_time_ms=request.response_time_ms,
        device_rtt_ms=request.device_rtt_ms,
        edits_in_window=request.edits_in_window,
    )

    next_response = None
    if result.next:
        next_response = NextQuestionResponse(
            question_id=result.next.question_id,
            prompt=result.next.prompt,
            answer_types=result.next.answer_types,
            ui=result.next.ui,
            options=result.next.options,
            context=result.next.context,
        )

    return SubmitAnswerResponse(
        accepted=result.accepted,
        validation_errors=result.validation_errors,
        flags_added=result.flags_added,
        scores=result.scores,
        next=next_response,
        overlay=result.overlay,
    )


# =============================================================================
# Party Management Endpoints
# =============================================================================

@router.post("/sessions/{session_id}/parties", response_model=AddPartyResponse)
async def add_party(
    session_id: str,
    request: AddPartyRequest,
    engine: IntakeEngine = Depends(get_engine),
):
    """Add a co-borrower or non-borrowing spouse"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        party_type = PartyType(request.party_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid party type: {request.party_type}"
        )

    party = engine.add_party(session, party_type, request.display_name)

    return AddPartyResponse(
        party_id=party.party_id,
        party_type=party.party_type,
        display_name=party.display_name,
    )


@router.get("/sessions/{session_id}/parties")
async def get_parties(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get all parties in session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "parties": [
            {
                "party_id": p.party_id,
                "party_type": p.party_type,
                "display_name": p.display_name,
                "is_complete": p.is_complete,
                "created_at": p.created_at.isoformat(),
            }
            for p in session.parties
        ]
    }


# =============================================================================
# Consent Management Endpoints
# =============================================================================

@router.post("/sessions/{session_id}/consents")
async def capture_consent(
    session_id: str,
    request: CaptureConsentRequest,
    http_request: Request,
    engine: IntakeEngine = Depends(get_engine),
):
    """Capture a consent response"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from ..runtime.models import ConsentRecord

    consent = ConsentRecord(
        consent_key=request.consent_key,
        accepted=request.accepted,
        version_hash=request.version_hash,
        ip_address=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent"),
    )

    session.consents[request.consent_key] = consent
    engine.storage.save_session(session)

    # Log consent event
    from ..runtime.models import EventType
    engine.storage.create_event(
        session_id=session_id,
        event_type=EventType.CONSENT_CAPTURED if request.accepted else EventType.CONSENT_DECLINED,
        payload={
            "consent_key": request.consent_key,
            "accepted": request.accepted,
            "version_hash": request.version_hash,
        },
    )

    return {"status": "captured", "consent_key": request.consent_key}


@router.get("/sessions/{session_id}/consents")
async def get_consents(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get all consent records for session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "consents": {
            key: {
                "accepted": c.accepted,
                "captured_at": c.captured_at.isoformat(),
                "version_hash": c.version_hash,
            }
            for key, c in session.consents.items()
        }
    }


# =============================================================================
# Session Completion Endpoints
# =============================================================================

@router.post("/sessions/{session_id}/complete", response_model=CompleteSessionResponse)
async def complete_session(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Complete the intake session and generate URLA payload"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == SessionStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Session already completed")

    result = engine.complete_session(session)

    return CompleteSessionResponse(
        status=result.status,
        urla_payload=result.urla_payload,
        scores=result.scores,
        flags=result.flags,
        sla_tasks_created=result.sla_tasks_created,
        redirect=result.redirect,
    )


# =============================================================================
# Coaching & Overlay Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/coaching")
async def get_coaching_suggestions(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get proactive coaching suggestions for LO"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    suggestions = engine.get_coaching_suggestions(session)
    return {"suggestions": suggestions}


@router.post("/sessions/{session_id}/overlays/{overlay_id}/dismiss")
async def dismiss_overlay(
    session_id: str,
    overlay_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Dismiss an active overlay"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    engine.dismiss_overlay(session, overlay_id)
    return {"status": "dismissed"}


# =============================================================================
# Audit Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/audit", response_model=AuditTrailResponse)
async def get_audit_trail(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get audit trail for session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = engine.get_audit_trail(session_id)
    chain_valid = engine.verify_audit_chain(session_id)

    return AuditTrailResponse(
        session_id=session_id,
        events=events,
        chain_valid=chain_valid,
    )


# =============================================================================
# Scores & Flags Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/scores")
async def get_scores(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get current scores for session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "truth_score": session.scores.underwriting_truth_score,
        "truth_band": session.scores.truth_band,
        "readiness_score": session.scores.lo_readiness_score,
        "hesitation_score": session.scores.hesitation_score,
        "hesitation_band": session.scores.hesitation_band,
        "breakdown": {
            "completeness": session.scores.score_breakdown.completeness,
            "internal_consistency": session.scores.score_breakdown.internal_consistency,
            "evidence_alignment": session.scores.score_breakdown.evidence_alignment,
            "behavioral_confidence": session.scores.score_breakdown.behavioral_confidence,
        },
    }


@router.get("/sessions/{session_id}/flags")
async def get_flags(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get current flags for session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "flags": [
            {
                "code": f.code,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "triggered_by": f.triggered_by,
                "triggered_at": f.triggered_at.isoformat(),
                "party_id": f.party_id,
            }
            for f in session.flags
        ]
    }


# =============================================================================
# Answer History Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/answers")
async def get_answers(
    session_id: str,
    party_id: Optional[str] = None,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get all answers for session or specific party"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if party_id:
        answers = session.party_answers.get(party_id, {})
    else:
        answers = session.answers

    return {"answers": answers}


@router.get("/sessions/{session_id}/edits")
async def get_edit_history(
    session_id: str,
    engine: IntakeEngine = Depends(get_engine),
):
    """Get edit history for session"""
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "edits": [
            {
                "question_id": e.question_id,
                "party_id": e.party_id,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "edited_at": e.edited_at.isoformat(),
            }
            for e in session.edits_history
        ]
    }
