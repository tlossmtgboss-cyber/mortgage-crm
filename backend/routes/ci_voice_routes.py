"""
Conversation Intelligence Voice Routes

API endpoints for the voice call analysis platform:
- Call recording management
- Transcription (Deepgram, AssemblyAI, Whisper)
- Post-call AI analysis with Claude
- QA scoring with mortgage rubrics
- Real-time assist (WebSocket)
- Coaching workflows (clips, assignments)
- Compliance monitoring
- Dashboard and metrics

This is separate from conversation_intelligence_routes.py which handles email/SMS channels.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from uuid import UUID
import json

from fastapi import (
    APIRouter, Depends, HTTPException, BackgroundTasks,
    WebSocket, WebSocketDisconnect, UploadFile, File, Query, Request, status
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversation-intelligence", tags=["Conversation Intelligence - Voice"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_current_user = None
_oauth2_scheme = None


def set_dependencies(user_dependency, oauth2=None):
    """Set the get_current_user dependency from main app."""
    global _get_current_user, _oauth2_scheme
    _get_current_user = user_dependency
    _oauth2_scheme = oauth2


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user dependency wrapper."""
    # Extract token from Authorization header
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

class RecordingCreateRequest(BaseModel):
    """Request to create a call recording entry."""
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    agent_id: int
    direction: str = Field(..., description="inbound or outbound")
    caller_number: Optional[str] = None
    callee_number: Optional[str] = None
    external_call_id: Optional[str] = None
    telephony_provider: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RecordingResponse(BaseModel):
    """Response for a call recording."""
    id: str
    loan_id: Optional[int]
    lead_id: Optional[int]
    agent_id: int
    direction: str
    status: str
    duration_seconds: Optional[int]
    audio_url: Optional[str]
    created_at: datetime


class TranscribeURLRequest(BaseModel):
    """Request to transcribe from audio URL."""
    audio_url: str
    provider: str = Field(default="deepgram", description="deepgram, assemblyai, or whisper")
    options: Optional[Dict[str, Any]] = None


class TranscriptionResponse(BaseModel):
    """Response from transcription."""
    transcription_id: str
    recording_id: str
    status: str
    transcript_text: Optional[str]
    word_count: Optional[int]
    segments: Optional[List[Dict[str, Any]]]
    speakers: Optional[Dict[str, str]]


class AnalysisRequest(BaseModel):
    """Request to analyze a transcribed call."""
    extract_topics: bool = True
    extract_action_items: bool = True
    extract_objections: bool = True
    extract_questions: bool = True
    check_compliance: bool = True
    custom_prompts: Optional[Dict[str, str]] = None


class AnalysisResponse(BaseModel):
    """Response from call analysis."""
    analysis_id: str
    recording_id: str
    status: str
    summary: Optional[str]
    key_topics: Optional[List[str]]
    action_items: Optional[List[Dict[str, Any]]]
    objections: Optional[List[Dict[str, Any]]]
    questions: Optional[List[Dict[str, Any]]]
    sentiment: Optional[Dict[str, Any]]
    talk_ratio: Optional[Dict[str, Any]]


class QAScorecardRequest(BaseModel):
    """Request to create QA scorecard."""
    rubric_id: Optional[str] = None
    use_llm_scoring: bool = True
    reviewer_id: Optional[int] = None


class QAScorecardResponse(BaseModel):
    """Response for QA scorecard."""
    scorecard_id: str
    recording_id: str
    rubric_name: str
    total_score: float
    max_possible_score: float
    grade: str
    items: List[Dict[str, Any]]
    recommendations: List[str]


class RealTimeSessionRequest(BaseModel):
    """Request to start real-time assist session."""
    agent_id: int
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    caller_number: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class RealTimeSessionResponse(BaseModel):
    """Response for real-time session."""
    session_id: str
    recording_id: str
    websocket_url: str
    status: str


class CoachingClipRequest(BaseModel):
    """Request to create a coaching clip."""
    recording_id: str
    title: str
    start_time: float
    end_time: float
    category: str = Field(default="general", description="best_practice, improvement, compliance, etc.")
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class CoachingClipResponse(BaseModel):
    """Response for coaching clip."""
    clip_id: str
    recording_id: str
    title: str
    duration_seconds: float
    category: str
    created_by: int


class CoachingAssignmentRequest(BaseModel):
    """Request to create coaching assignment."""
    clip_id: str
    assigned_to: int
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "medium"


class CoachingAssignmentResponse(BaseModel):
    """Response for coaching assignment."""
    assignment_id: str
    clip_id: str
    assigned_to: int
    assigned_by: int
    status: str
    due_date: Optional[datetime]


class DashboardFilters(BaseModel):
    """Filters for dashboard queries."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    agent_ids: Optional[List[int]] = None
    team_id: Optional[int] = None


# =============================================================================
# RECORDING ENDPOINTS
# =============================================================================

@router.post("/recordings", response_model=RecordingResponse)
async def create_recording(
    request: RecordingCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new call recording entry."""
    try:
        import uuid
        recording_id = str(uuid.uuid4())

        result = db.execute(text("""
            INSERT INTO ci_call_recordings (
                id, loan_id, lead_id, agent_user_id, direction,
                phone_from, phone_to, external_call_id,
                status, metadata, started_at
            ) VALUES (
                :id, :loan_id, :lead_id, :agent_user_id, :direction,
                :phone_from, :phone_to, :external_call_id,
                'pending', :metadata, CURRENT_TIMESTAMP
            )
        """), {
            "id": recording_id,
            "loan_id": request.loan_id,
            "lead_id": request.lead_id,
            "agent_user_id": request.agent_id,
            "direction": request.direction,
            "phone_from": request.caller_number,
            "phone_to": request.callee_number,
            "external_call_id": request.external_call_id,
            "metadata": json.dumps(request.metadata) if request.metadata else None
        })
        db.commit()

        # Fetch the created record
        row = db.execute(text("""
            SELECT id, loan_id, lead_id, agent_user_id, direction, status,
                   duration_seconds, recording_url, created_at
            FROM ci_call_recordings WHERE id = :id
        """), {"id": recording_id}).fetchone()

        return RecordingResponse(
            id=str(row[0]),
            loan_id=row[1],
            lead_id=row[2],
            agent_id=row[3],
            direction=row[4],
            status=row[5],
            duration_seconds=row[6],
            audio_url=row[7],
            created_at=row[8]
        )

    except Exception as e:
        logger.error(f"Error creating recording: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CARPLAY / MOBILE QUICK UPLOAD (Base64)
# =============================================================================

class QuickUploadRequest(BaseModel):
    """Request for quick base64 audio upload from CarPlay/mobile."""
    audio_base64: str = Field(..., description="Base64 encoded audio data")
    duration_seconds: int = Field(..., description="Duration of recording in seconds")
    file_name: str = Field(default="recording.m4a", description="Original filename")
    direction: str = Field(default="outbound", description="Call direction")
    source: str = Field(default="mobile", description="Source app (carplay, mobile)")
    process_immediately: bool = Field(default=True, description="Start AI processing immediately")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class QuickUploadResponse(BaseModel):
    """Response from quick upload."""
    recording_id: str
    status: str
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    sentiment: Optional[str] = None
    duration: int
    message: str


@router.post("/recordings/quick-upload", response_model=QuickUploadResponse)
async def quick_upload_recording(
    request: QuickUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Quick upload endpoint for CarPlay and mobile apps.
    Accepts base64 audio and returns AI analysis results.
    """
    import uuid
    import base64
    import tempfile
    import os as os_module

    try:
        recording_id = str(uuid.uuid4())
        # Handle both dict and User object
        if hasattr(current_user, 'id'):
            user_id = current_user.id
        elif isinstance(current_user, dict):
            user_id = current_user.get("id") or current_user.get("user_id")
        else:
            user_id = None
        if not user_id:
            raise HTTPException(status_code=401, detail="Could not determine user identity")

        logger.info(f"[QuickUpload] Receiving {request.duration_seconds}s recording from {request.source}")

        # Decode base64 audio
        try:
            audio_data = base64.b64decode(request.audio_base64)
            logger.info(f"[QuickUpload] Decoded {len(audio_data)} bytes of audio")
        except Exception as e:
            logger.error(f"[QuickUpload] Base64 decode error: {e}")
            raise HTTPException(status_code=400, detail="Invalid base64 audio data")

        # Save to temp file for processing
        temp_dir = tempfile.gettempdir()
        audio_path = os_module.path.join(temp_dir, f"{recording_id}.m4a")
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        logger.info(f"[QuickUpload] Saved audio to {audio_path}")

        # Create recording entry
        metadata = request.metadata or {}
        metadata["source"] = request.source
        metadata["quick_upload"] = True

        db.execute(text("""
            INSERT INTO ci_call_recordings (
                id, agent_user_id, direction, duration_seconds,
                status, metadata, started_at
            ) VALUES (
                :id, :agent_user_id, :direction, :duration,
                'processing', :metadata, CURRENT_TIMESTAMP
            )
        """), {
            "id": recording_id,
            "agent_user_id": user_id,
            "direction": request.direction,
            "duration": request.duration_seconds,
            "metadata": json.dumps(metadata)
        })
        db.commit()

        # Process with AI (transcribe + analyze)
        summary = "Call recorded successfully"
        key_points = []
        action_items = []
        sentiment = "neutral"

        if request.process_immediately:
            try:
                # Try to transcribe with Whisper/Deepgram
                transcript = await transcribe_audio_file(audio_path)
                if transcript:
                    logger.info(f"[QuickUpload] Transcribed: {transcript[:100]}...")

                    # Analyze with Claude
                    analysis = await analyze_call_transcript(transcript, request.direction)
                    summary = analysis.get("summary", "Call recorded and transcribed")
                    key_points = analysis.get("key_points", [])
                    action_items = analysis.get("action_items", [])
                    sentiment = analysis.get("sentiment", "neutral")

                    # Update recording with results
                    db.execute(text("""
                        UPDATE ci_call_recordings
                        SET status = 'analyzed',
                            transcript_text = :transcript,
                            ai_summary = :summary,
                            sentiment_score = :sentiment
                        WHERE id = :id
                    """), {
                        "id": recording_id,
                        "transcript": transcript,
                        "summary": summary,
                        "sentiment": sentiment
                    })
                    db.commit()
                    logger.info(f"[QuickUpload] Analysis complete for {recording_id}")
            except Exception as e:
                logger.error(f"[QuickUpload] Processing error: {e}")
                summary = "Call recorded. Processing will complete shortly."

        # Cleanup temp file
        try:
            os_module.remove(audio_path)
        except OSError:
            pass

        return QuickUploadResponse(
            recording_id=recording_id,
            status="analyzed" if request.process_immediately else "pending",
            summary=summary,
            key_points=key_points,
            action_items=action_items,
            sentiment=sentiment,
            duration=request.duration_seconds,
            message="Recording processed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[QuickUpload] Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def transcribe_audio_file(audio_path: str) -> Optional[str]:
    """Transcribe audio file using available service."""
    import subprocess

    # Try Whisper via OpenAI API
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_path, "rb") as f:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        files={"file": ("audio.m4a", f, "audio/mp4")},
                        data={"model": "whisper-1"}
                    )
                if response.status_code == 200:
                    return response.json().get("text", "")
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")

    return None


async def analyze_call_transcript(transcript: str, direction: str) -> Dict[str, Any]:
    """Analyze call transcript with Claude."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"summary": "Transcript recorded", "sentiment": "neutral"}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""Analyze this {direction} call transcript for a mortgage loan officer.
Provide a JSON response with:
- summary: 1-2 sentence summary
- key_points: list of key points discussed
- action_items: list of follow-up actions needed
- sentiment: positive, neutral, or negative

Transcript:
{transcript}

Respond only with valid JSON."""
            }]
        )

        result_text = response.content[0].text
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logger.error(f"Claude analysis error: {e}")

    return {"summary": transcript[:200], "sentiment": "neutral", "key_points": [], "action_items": []}


@router.get("/recordings/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a specific call recording."""
    try:
        result = db.execute(text("""
            SELECT id, loan_id, lead_id, agent_user_id, direction, status,
                   duration_seconds, recording_url, created_at
            FROM ci_call_recordings
            WHERE id = :id
        """), {"id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")

        created_at = row[8]
        if created_at and hasattr(created_at, 'isoformat'):
            created_at = created_at.isoformat()

        return RecordingResponse(
            id=str(row[0]),
            loan_id=row[1],
            lead_id=row[2],
            agent_id=row[3],
            direction=row[4],
            status=row[5],
            duration_seconds=row[6],
            audio_url=row[7],
            created_at=created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/recordings")
async def list_recordings(
    agent_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List call recordings with filters."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if agent_id:
            filters.append("agent_user_id = :agent_id")
            params["agent_user_id"] = agent_id
        if loan_id:
            filters.append("loan_id = :loan_id")
            params["loan_id"] = loan_id
        if status:
            filters.append("status = :status")
            params["status"] = status
        if start_date:
            filters.append("created_at >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("created_at <= :end_date")
            params["end_date"] = end_date

        where_clause = " AND ".join(filters)

        sql = """
            SELECT id, loan_id, lead_id, agent_user_id, direction, status,
                   duration_seconds, recording_url, created_at
            FROM ci_call_recordings
            WHERE """ + where_clause + """
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), params)

        recordings = []
        for row in result.fetchall():
            created_at = row[8]
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            recordings.append({
                "id": str(row[0]),
                "loan_id": row[1],
                "lead_id": row[2],
                "agent_id": row[3],
                "direction": row[4],
                "status": row[5],
                "duration_seconds": row[6],
                "audio_url": row[7],
                "created_at": created_at
            })

        # Get total count
        count_sql = "SELECT COUNT(*) FROM ci_call_recordings WHERE " + where_clause
        count_result = db.execute(text(count_sql), params)
        total = count_result.fetchone()[0]

        return {
            "recordings": recordings,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        error_str = str(e).lower()
        # Handle missing table gracefully - return empty list
        if "undefined" in error_str and "table" in error_str or "does not exist" in error_str:
            logger.warning(f"CI recordings table not found, returning empty list: {str(e)}")
            return {"recordings": [], "total": 0, "limit": limit, "offset": offset}
        logger.error(f"Error listing recordings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/recordings/{recording_id}/upload")
async def upload_audio(
    recording_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Upload audio file for a recording."""
    try:
        # Verify recording exists
        result = db.execute(text("""
            SELECT id, status FROM ci_call_recordings WHERE id = :id
        """), {"id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")

        # Read file content
        content = await file.read()
        file_size = len(content)

        # In production, upload to S3/GCS and get URL
        # For now, store locally or use placeholder
        audio_url = f"/api/v1/conversation-intelligence/recordings/{recording_id}/audio"

        # Update recording
        db.execute(text("""
            UPDATE ci_call_recordings
            SET audio_url = :audio_url,
                file_size_bytes = :file_size,
                audio_format = :format,
                status = 'uploaded',
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": recording_id,
            "audio_url": audio_url,
            "file_size": file_size,
            "format": file.content_type
        })
        db.commit()

        return {
            "status": "success",
            "recording_id": recording_id,
            "audio_url": audio_url,
            "file_size": file_size
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error uploading audio: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# TRANSCRIPTION ENDPOINTS
# =============================================================================

@router.post("/recordings/{recording_id}/transcribe", response_model=TranscriptionResponse)
async def transcribe_recording(
    recording_id: str,
    request: TranscribeURLRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Transcribe a call recording."""
    try:
        import uuid
        transcription_id = str(uuid.uuid4())

        # Verify recording exists
        result = db.execute(text("""
            SELECT id, status, audio_url FROM ci_call_recordings WHERE id = :id
        """), {"id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")

        # Create transcription record
        db.execute(text("""
            INSERT INTO ci_call_transcriptions (
                id, recording_id, provider, status, settings
            ) VALUES (
                :id, :recording_id, :provider, 'processing', :settings
            )
        """), {
            "id": transcription_id,
            "recording_id": recording_id,
            "provider": request.provider,
            "settings": json.dumps(request.options) if request.options else None
        })
        db.commit()

        # Start transcription in background
        background_tasks.add_task(
            process_transcription,
            transcription_id=transcription_id,
            recording_id=recording_id,
            audio_url=request.audio_url,
            provider=request.provider,
            options=request.options
        )

        return TranscriptionResponse(
            transcription_id=transcription_id,
            recording_id=recording_id,
            status="processing",
            transcript_text=None,
            word_count=None,
            segments=None,
            speakers=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting transcription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_transcription(
    transcription_id: str,
    recording_id: str,
    audio_url: str,
    provider: str,
    options: Optional[Dict[str, Any]]
):
    """Background task to process transcription."""
    try:
        from services.ci_transcription_service import TranscriptionService
        from database import get_db

        service = TranscriptionService(primary_provider=provider)
        result = await service.transcribe_audio(
            audio_url=audio_url,
            options=options or {}
        )

        # Get new DB session for background task
        db = next(get_db())

        try:
            if result.get("status") == "success":
                # Update transcription record
                db.execute(text("""
                    UPDATE ci_call_transcriptions
                    SET status = 'completed',
                        transcript_text = :transcript,
                        word_count = :word_count,
                        confidence_score = :confidence,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": transcription_id,
                    "transcript": result.get("transcript"),
                    "word_count": result.get("word_count"),
                    "confidence": result.get("confidence")
                })

                # Insert segments
                for segment in result.get("segments", []):
                    db.execute(text("""
                        INSERT INTO ci_transcription_segments (
                            transcription_id, speaker_label, start_time, end_time,
                            text, confidence, word_timestamps
                        ) VALUES (
                            :transcription_id, :speaker, :start_time, :end_time,
                            :text, :confidence, :word_timestamps
                        )
                    """), {
                        "transcription_id": transcription_id,
                        "speaker": segment.get("speaker"),
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "text": segment.get("text"),
                        "confidence": segment.get("confidence"),
                        "word_timestamps": json.dumps(segment.get("words", []))
                    })

                # Update recording status
                db.execute(text("""
                    UPDATE ci_call_recordings
                    SET status = 'transcribed', updated_at = NOW()
                    WHERE id = :id
                """), {"id": recording_id})

                db.commit()

                # Trigger Call Monitoring AI agents
                try:
                    from services.call_monitoring.ci_integration_service import trigger_call_monitoring_agents
                    logger.info(f"Triggering Call Monitoring agents for recording {recording_id}")
                    asyncio.create_task(
                        trigger_call_monitoring_agents(db, recording_id, transcription_id)
                    )
                except Exception as agent_error:
                    logger.warning(f"Could not trigger Call Monitoring agents: {agent_error}")
                    # Non-blocking - transcription still succeeded

            else:
                # Mark as failed
                db.execute(text("""
                    UPDATE ci_call_transcriptions
                    SET status = 'failed',
                        error_message = :error,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": transcription_id,
                    "error": result.get("error", "Unknown error")
                })

            db.commit()

        finally:
            db.close()

    except SQLAlchemyError as e:
        logger.error(f"Transcription processing error: {e}")


@router.get("/recordings/{recording_id}/transcription", response_model=TranscriptionResponse)
async def get_transcription(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get transcription for a recording."""
    try:
        result = db.execute(text("""
            SELECT t.id, t.recording_id, t.status, t.transcript_text,
                   t.word_count, t.speaker_mapping
            FROM ci_call_transcriptions t
            WHERE t.recording_id = :recording_id
            ORDER BY t.created_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transcription not found")

        # Get segments
        segments_result = db.execute(text("""
            SELECT speaker_label, start_time, end_time, text, confidence
            FROM ci_transcription_segments
            WHERE transcription_id = :id
            ORDER BY start_time
        """), {"id": row[0]})

        segments = []
        for seg in segments_result.fetchall():
            segments.append({
                "speaker": seg[0],
                "start_time": float(seg[1]) if seg[1] else 0,
                "end_time": float(seg[2]) if seg[2] else 0,
                "text": seg[3],
                "confidence": float(seg[4]) if seg[4] else None
            })

        return TranscriptionResponse(
            transcription_id=str(row[0]),
            recording_id=str(row[1]),
            status=row[2],
            transcript_text=row[3],
            word_count=row[4],
            segments=segments,
            speakers=row[5] if row[5] else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ANALYSIS ENDPOINTS
# =============================================================================

@router.post("/recordings/{recording_id}/analyze", response_model=AnalysisResponse)
async def analyze_recording(
    recording_id: str,
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Analyze a transcribed call with Claude."""
    try:
        import uuid
        analysis_id = str(uuid.uuid4())

        # Verify transcription exists
        result = db.execute(text("""
            SELECT t.id, t.transcript_text
            FROM ci_call_transcriptions t
            WHERE t.recording_id = :recording_id
            AND t.status = 'completed'
            ORDER BY t.created_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=400,
                detail="No completed transcription found for this recording"
            )

        transcription_id = row[0]

        # Create analysis record
        db.execute(text("""
            INSERT INTO ci_call_analyses (
                id, recording_id, transcription_id, status, analysis_config
            ) VALUES (
                :id, :recording_id, :transcription_id, 'processing', :config
            )
        """), {
            "id": analysis_id,
            "recording_id": recording_id,
            "transcription_id": transcription_id,
            "config": json.dumps({
                "extract_topics": request.extract_topics,
                "extract_action_items": request.extract_action_items,
                "extract_objections": request.extract_objections,
                "extract_questions": request.extract_questions,
                "check_compliance": request.check_compliance
            })
        })
        db.commit()

        # Start analysis in background
        background_tasks.add_task(
            process_analysis,
            analysis_id=analysis_id,
            recording_id=recording_id,
            transcription_id=str(transcription_id),
            config=request
        )

        return AnalysisResponse(
            analysis_id=analysis_id,
            recording_id=recording_id,
            status="processing",
            summary=None,
            key_topics=None,
            action_items=None,
            objections=None,
            questions=None,
            sentiment=None,
            talk_ratio=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_analysis(
    analysis_id: str,
    recording_id: str,
    transcription_id: str,
    config: AnalysisRequest
):
    """Background task to process call analysis."""
    try:
        from services.ci_analysis_service import CallAnalysisService
        from database import get_db

        service = CallAnalysisService()

        # Get DB session
        db = next(get_db())

        try:
            # Get transcript
            result = db.execute(text("""
                SELECT transcript_text FROM ci_call_transcriptions WHERE id = :id
            """), {"id": transcription_id})
            row = result.fetchone()

            if not row or not row[0]:
                raise Exception("Transcript not found")

            transcript = row[0]

            # Get segments for speaker analysis
            segments_result = db.execute(text("""
                SELECT speaker_label, start_time, end_time, text
                FROM ci_transcription_segments
                WHERE transcription_id = :id
                ORDER BY start_time
            """), {"id": transcription_id})

            segments = []
            for seg in segments_result.fetchall():
                segments.append({
                    "speaker": seg[0],
                    "start_time": float(seg[1]) if seg[1] else 0,
                    "end_time": float(seg[2]) if seg[2] else 0,
                    "text": seg[3]
                })

            # Run analysis
            analysis_result = await service.analyze_call(
                transcript=transcript,
                segments=segments,
                extract_topics=config.extract_topics,
                extract_action_items=config.extract_action_items,
                extract_objections=config.extract_objections,
                extract_questions=config.extract_questions
            )

            # Update analysis record
            db.execute(text("""
                UPDATE ci_call_analyses
                SET status = 'completed',
                    summary = :summary,
                    key_topics = :topics,
                    action_items = :action_items,
                    objections_detected = :objections,
                    questions_raised = :questions,
                    sentiment_analysis = :sentiment,
                    talk_ratio = :talk_ratio,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": analysis_id,
                "summary": analysis_result.get("summary"),
                "topics": json.dumps(analysis_result.get("topics", [])),
                "action_items": json.dumps(analysis_result.get("action_items", [])),
                "objections": json.dumps(analysis_result.get("objections", [])),
                "questions": json.dumps(analysis_result.get("questions", [])),
                "sentiment": json.dumps(analysis_result.get("sentiment", {})),
                "talk_ratio": json.dumps(analysis_result.get("talk_ratio", {}))
            })

            # Update recording status
            db.execute(text("""
                UPDATE ci_call_recordings
                SET status = 'analyzed', updated_at = NOW()
                WHERE id = :id
            """), {"id": recording_id})

            db.commit()

        finally:
            db.close()

    except SQLAlchemyError as e:
        logger.error(f"Analysis processing error: {e}")
        # Mark as failed
        try:
            db = next(get_db())
            db.execute(text("""
                UPDATE ci_call_analyses
                SET status = 'failed', error_message = :error, updated_at = NOW()
                WHERE id = :id
            """), {"id": analysis_id, "error": "Internal server error"})
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"Error closing db after analysis failure: {e}")


@router.get("/recordings/{recording_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get analysis for a recording."""
    try:
        result = db.execute(text("""
            SELECT id, recording_id, status, summary, key_topics,
                   action_items, objections_detected, questions_raised,
                   sentiment_analysis, talk_ratio
            FROM ci_call_analyses
            WHERE recording_id = :recording_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Analysis not found")

        return AnalysisResponse(
            analysis_id=str(row[0]),
            recording_id=str(row[1]),
            status=row[2],
            summary=row[3],
            key_topics=json.loads(row[4]) if row[4] else None,
            action_items=json.loads(row[5]) if row[5] else None,
            objections=json.loads(row[6]) if row[6] else None,
            questions=json.loads(row[7]) if row[7] else None,
            sentiment=json.loads(row[8]) if row[8] else None,
            talk_ratio=json.loads(row[9]) if row[9] else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# QA SCORING ENDPOINTS
# =============================================================================

@router.post("/recordings/{recording_id}/qa-score", response_model=QAScorecardResponse)
async def create_qa_scorecard(
    recording_id: str,
    request: QAScorecardRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create QA scorecard for a recording."""
    try:
        from services.ci_qa_scoring_service import QAScoringService
        import uuid

        scorecard_id = str(uuid.uuid4())

        # Verify recording has analysis
        result = db.execute(text("""
            SELECT a.id, t.transcript_text, t.id as transcription_id
            FROM ci_call_recordings r
            LEFT JOIN ci_call_analyses a ON a.recording_id = r.id
            LEFT JOIN ci_call_transcriptions t ON t.recording_id = r.id
            WHERE r.id = :recording_id
            ORDER BY a.created_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        if not row or not row[1]:
            raise HTTPException(
                status_code=400,
                detail="Recording must be transcribed before QA scoring"
            )

        transcript = row[1]

        # Get or use default rubric
        rubric_id = request.rubric_id
        rubric_name = "Default Mortgage QA Rubric"

        if rubric_id:
            rubric_result = db.execute(text("""
                SELECT id, name FROM ci_qa_rubrics WHERE id = :id AND is_active = true
            """), {"id": rubric_id})
            rubric_row = rubric_result.fetchone()
            if rubric_row:
                rubric_name = rubric_row[1]

        # Get segments for context
        segments_result = db.execute(text("""
            SELECT speaker_label, text FROM ci_transcription_segments
            WHERE transcription_id = :id ORDER BY start_time
        """), {"id": row[2]})

        segments = [{"speaker": s[0], "text": s[1]} for s in segments_result.fetchall()]

        # Score the call
        service = QAScoringService()
        scoring_result = await service.score_call(
            transcript=transcript,
            segments=segments,
            rubric_id=rubric_id,
            use_llm=request.use_llm_scoring
        )

        # Create scorecard record
        db.execute(text("""
            INSERT INTO ci_qa_scorecards (
                id, recording_id, rubric_id, reviewer_id, reviewer_type,
                total_score, max_possible_score, percentage_score,
                grade, strengths, improvements, recommendations,
                status
            ) VALUES (
                :id, :recording_id, :rubric_id, :reviewer_id, :reviewer_type,
                :total_score, :max_score, :percentage,
                :grade, :strengths, :improvements, :recommendations,
                'completed'
            )
        """), {
            "id": scorecard_id,
            "recording_id": recording_id,
            "rubric_id": rubric_id,
            "reviewer_id": request.reviewer_id or current_user.get("id"),
            "reviewer_type": "ai" if request.use_llm_scoring else "manual",
            "total_score": scoring_result.get("total_score", 0),
            "max_score": scoring_result.get("max_possible_score", 100),
            "percentage": scoring_result.get("percentage", 0),
            "grade": scoring_result.get("grade", "N/A"),
            "strengths": json.dumps(scoring_result.get("strengths", [])),
            "improvements": json.dumps(scoring_result.get("improvements", [])),
            "recommendations": json.dumps(scoring_result.get("recommendations", []))
        })

        # Insert scorecard items
        for item in scoring_result.get("items", []):
            db.execute(text("""
                INSERT INTO ci_qa_scorecard_items (
                    scorecard_id, criterion_id, criterion_name, category,
                    score, max_score, weight, evidence, notes
                ) VALUES (
                    :scorecard_id, :criterion_id, :name, :category,
                    :score, :max_score, :weight, :evidence, :notes
                )
            """), {
                "scorecard_id": scorecard_id,
                "criterion_id": item.get("criterion_id"),
                "name": item.get("name"),
                "category": item.get("category"),
                "score": item.get("score", 0),
                "max_score": item.get("max_score", 10),
                "weight": item.get("weight", 1.0),
                "evidence": item.get("evidence"),
                "notes": item.get("notes")
            })

        # Update recording status
        db.execute(text("""
            UPDATE ci_call_recordings
            SET status = 'scored', updated_at = NOW()
            WHERE id = :id
        """), {"id": recording_id})

        db.commit()

        return QAScorecardResponse(
            scorecard_id=scorecard_id,
            recording_id=recording_id,
            rubric_name=rubric_name,
            total_score=scoring_result.get("total_score", 0),
            max_possible_score=scoring_result.get("max_possible_score", 100),
            grade=scoring_result.get("grade", "N/A"),
            items=scoring_result.get("items", []),
            recommendations=scoring_result.get("recommendations", [])
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating QA scorecard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/recordings/{recording_id}/qa-scorecards")
async def get_qa_scorecards(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all QA scorecards for a recording."""
    try:
        result = db.execute(text("""
            SELECT s.id, s.rubric_id, r.name as rubric_name,
                   s.total_score, s.max_possible_score, s.percentage_score,
                   s.grade, s.reviewer_type, s.created_at
            FROM ci_qa_scorecards s
            LEFT JOIN ci_qa_rubrics r ON r.id = s.rubric_id
            WHERE s.recording_id = :recording_id
            ORDER BY s.created_at DESC
        """), {"recording_id": recording_id})

        scorecards = []
        for row in result.fetchall():
            scorecards.append({
                "id": str(row[0]),
                "rubric_id": str(row[1]) if row[1] else None,
                "rubric_name": row[2] or "Default",
                "total_score": float(row[3]) if row[3] else 0,
                "max_possible_score": float(row[4]) if row[4] else 100,
                "percentage": float(row[5]) if row[5] else 0,
                "grade": row[6],
                "reviewer_type": row[7],
                "created_at": row[8].isoformat() if row[8] else None
            })

        return {"scorecards": scorecards}

    except Exception as e:
        logger.error(f"Error getting QA scorecards: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/qa-rubrics")
async def list_qa_rubrics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List available QA rubrics."""
    try:
        result = db.execute(text("""
            SELECT id, name, description, category, max_points,
                   weight, required, created_at
            FROM ci_qa_rubrics
            WHERE is_active = true
            ORDER BY category, name
        """))

        rubrics = []
        for row in result.fetchall():
            created_at = row[7]
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            rubrics.append({
                "id": str(row[0]),
                "name": row[1],
                "description": row[2],
                "category": row[3],
                "maxTotalScore": int(row[4]) if row[4] else 10,
                "weight": float(row[5]) if row[5] else 1.0,
                "isDefault": bool(row[6]),  # using 'required' as proxy for default
                "created_at": created_at
            })

        return {"rubrics": rubrics}

    except Exception as e:
        error_str = str(e).lower()
        # Handle missing table gracefully - return empty list
        if "undefined" in error_str and "table" in error_str or "does not exist" in error_str:
            logger.warning(f"CI QA rubrics table not found, returning empty list: {str(e)}")
            return {"rubrics": []}
        logger.error(f"Error listing rubrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# REAL-TIME ASSIST ENDPOINTS
# =============================================================================

@router.post("/realtime/sessions", response_model=RealTimeSessionResponse)
async def create_realtime_session(
    request: RealTimeSessionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a real-time assist session."""
    try:
        import uuid

        session_id = str(uuid.uuid4())
        recording_id = str(uuid.uuid4())

        # Create recording first
        db.execute(text("""
            INSERT INTO ci_call_recordings (
                id, loan_id, lead_id, agent_user_id, direction,
                phone_from, status, started_at
            ) VALUES (
                :id, :loan_id, :lead_id, :agent_user_id, 'outbound',
                :phone_from, 'in_progress', CURRENT_TIMESTAMP
            )
        """), {
            "id": recording_id,
            "loan_id": request.loan_id,
            "lead_id": request.lead_id,
            "agent_user_id": request.agent_id,
            "phone_from": request.caller_number
        })

        # Create session
        db.execute(text("""
            INSERT INTO ci_realtime_sessions (
                id, recording_id, agent_user_id, status, settings
            ) VALUES (
                :id, :recording_id, :agent_user_id, 'active', :settings
            )
        """), {
            "id": session_id,
            "recording_id": recording_id,
            "agent_user_id": request.agent_id,
            "settings": json.dumps(request.context) if request.context else None
        })

        db.commit()

        # Generate WebSocket URL
        ws_url = f"/api/v1/conversation-intelligence/realtime/sessions/{session_id}/ws"

        return RealTimeSessionResponse(
            session_id=session_id,
            recording_id=recording_id,
            websocket_url=ws_url,
            status="active"
        )

    except SQLAlchemyError as e:
        logger.error(f"Error creating realtime session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/realtime/sessions/{session_id}/ws")
async def realtime_websocket(
    websocket: WebSocket,
    session_id: str
):
    """WebSocket endpoint for real-time coaching."""
    await websocket.accept()

    try:
        from services.ci_realtime_assist_service import RealtimeAssistService

        service = RealtimeAssistService()

        # Define callback for suggestions
        async def send_suggestion(suggestion: Dict[str, Any]):
            await websocket.send_json({
                "type": "suggestion",
                "data": suggestion
            })

        # Start session
        await service.start_session(
            session_id=session_id,
            callback=send_suggestion
        )

        # Send confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id
        })

        # Process incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")

                if message_type == "transcript_update":
                    # Process new transcript text
                    text = data.get("text", "")
                    speaker = data.get("speaker", "unknown")
                    timestamp = data.get("timestamp", 0)

                    await service.process_transcript_update(
                        session_id=session_id,
                        text=text,
                        speaker=speaker,
                        timestamp=timestamp
                    )

                elif message_type == "end_call":
                    # End the session
                    await service.end_session(session_id)
                    await websocket.send_json({
                        "type": "session_ended",
                        "session_id": session_id
                    })
                    break

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        try:
            await websocket.close()
        except Exception as e:
            logger.warning(f"Error closing WebSocket: {e}")


@router.post("/realtime/sessions/{session_id}/end")
async def end_realtime_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """End a real-time assist session."""
    try:
        # Get session info
        result = db.execute(text("""
            SELECT id, recording_id, started_at
            FROM ci_realtime_sessions
            WHERE id = :id
        """), {"id": session_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        # Calculate duration
        started_at = row[2]
        duration = (datetime.now(timezone.utc) - started_at).total_seconds() if started_at else 0

        # Update session
        db.execute(text("""
            UPDATE ci_realtime_sessions
            SET status = 'completed',
                ended_at = NOW(),
                duration_seconds = :duration
            WHERE id = :id
        """), {"id": session_id, "duration": int(duration)})

        # Update recording
        db.execute(text("""
            UPDATE ci_call_recordings
            SET status = 'completed',
                ended_at = NOW(),
                duration_seconds = :duration
            WHERE id = :recording_id
        """), {"recording_id": row[1], "duration": int(duration)})

        db.commit()

        return {
            "status": "success",
            "session_id": session_id,
            "duration_seconds": int(duration)
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# COACHING ENDPOINTS
# =============================================================================

@router.post("/coaching/clips", response_model=CoachingClipResponse)
async def create_coaching_clip(
    request: CoachingClipRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a coaching clip from a recording."""
    try:
        import uuid
        clip_id = str(uuid.uuid4())

        # Verify recording exists
        result = db.execute(text("""
            SELECT id, audio_url FROM ci_call_recordings WHERE id = :id
        """), {"id": request.recording_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")

        duration = request.end_time - request.start_time
        user_id = current_user.get("id") or current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Could not determine user identity")

        # Create clip
        db.execute(text("""
            INSERT INTO ci_coaching_clips (
                id, recording_id, title, description, category,
                start_time, end_time, duration_seconds,
                tags, created_by
            ) VALUES (
                :id, :recording_id, :title, :description, :category,
                :start_time, :end_time, :duration,
                :tags, :created_by
            )
        """), {
            "id": clip_id,
            "recording_id": request.recording_id,
            "title": request.title,
            "description": request.description,
            "category": request.category,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "duration": duration,
            "tags": json.dumps(request.tags) if request.tags else None,
            "created_by": user_id
        })

        db.commit()

        return CoachingClipResponse(
            clip_id=clip_id,
            recording_id=request.recording_id,
            title=request.title,
            duration_seconds=duration,
            category=request.category,
            created_by=user_id
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating clip: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/coaching/clips")
async def list_coaching_clips(
    category: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List coaching clips with filters."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if category:
            filters.append("c.category = :category")
            params["category"] = category
        if agent_id:
            filters.append("r.agent_user_id = :agent_id")
            params["agent_user_id"] = agent_id

        where_clause = " AND ".join(filters)

        sql = """
            SELECT c.id, c.recording_id, c.title, c.description,
                   c.category, c.duration_seconds, c.view_count,
                   c.created_at, u.email as created_by_email
            FROM ci_coaching_clips c
            JOIN ci_call_recordings r ON r.id = c.recording_id
            LEFT JOIN users u ON u.id = c.created_by
            WHERE """ + where_clause + """
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), params)

        clips = []
        for row in result.fetchall():
            clips.append({
                "id": str(row[0]),
                "recording_id": str(row[1]),
                "title": row[2],
                "description": row[3],
                "category": row[4],
                "duration_seconds": float(row[5]) if row[5] else 0,
                "view_count": row[6] or 0,
                "created_at": row[7].isoformat() if row[7] else None,
                "created_by": row[8]
            })

        return {"clips": clips, "limit": limit, "offset": offset}

    except Exception as e:
        logger.error(f"Error listing clips: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/coaching/assignments", response_model=CoachingAssignmentResponse)
async def create_coaching_assignment(
    request: CoachingAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Assign a coaching clip to an agent."""
    try:
        import uuid
        assignment_id = str(uuid.uuid4())
        user_id = current_user.get("id") or current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Could not determine user identity")

        # Verify clip exists
        result = db.execute(text("""
            SELECT id FROM ci_coaching_clips WHERE id = :id
        """), {"id": request.clip_id})

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Clip not found")

        # Create assignment
        db.execute(text("""
            INSERT INTO ci_coaching_assignments (
                id, clip_id, assigned_to, assigned_by,
                title, description, due_date, priority, status
            ) VALUES (
                :id, :clip_id, :assigned_to, :assigned_by,
                :title, :description, :due_date, :priority, 'pending'
            )
        """), {
            "id": assignment_id,
            "clip_id": request.clip_id,
            "assigned_to": request.assigned_to,
            "assigned_by": user_id,
            "title": request.title,
            "description": request.description,
            "due_date": request.due_date,
            "priority": request.priority
        })

        db.commit()

        return CoachingAssignmentResponse(
            assignment_id=assignment_id,
            clip_id=request.clip_id,
            assigned_to=request.assigned_to,
            assigned_by=user_id,
            status="pending",
            due_date=request.due_date
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating assignment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/coaching/assignments")
async def list_coaching_assignments(
    assigned_to: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List coaching assignments with filters."""
    try:
        filters = ["1=1"]
        params = {"limit": limit}

        if assigned_to:
            filters.append("a.assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to
        if status:
            filters.append("a.status = :status")
            params["status"] = status

        where_clause = " AND ".join(filters)

        sql = """
            SELECT a.id, a.clip_id, c.title as clip_title,
                   a.assigned_to, a.assigned_by, a.title,
                   a.status, a.due_date, a.created_at
            FROM ci_coaching_assignments a
            JOIN ci_coaching_clips c ON c.id = a.clip_id
            WHERE """ + where_clause + """
            ORDER BY a.due_date ASC NULLS LAST, a.created_at DESC
            LIMIT :limit
        """
        result = db.execute(text(sql), params)

        assignments = []
        for row in result.fetchall():
            assignments.append({
                "id": str(row[0]),
                "clip_id": str(row[1]),
                "clip_title": row[2],
                "assigned_to": row[3],
                "assigned_by": row[4],
                "title": row[5],
                "status": row[6],
                "due_date": row[7].isoformat() if row[7] else None,
                "created_at": row[8].isoformat() if row[8] else None
            })

        return {"assignments": assignments}

    except Exception as e:
        logger.error(f"Error listing assignments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/coaching/assignments/{assignment_id}/complete")
async def complete_coaching_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Mark a coaching assignment as completed."""
    try:
        db.execute(text("""
            UPDATE ci_coaching_assignments
            SET status = 'completed',
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": assignment_id})

        db.commit()

        return {"status": "success", "assignment_id": assignment_id}

    except SQLAlchemyError as e:
        logger.error(f"Error completing assignment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard/team")
async def get_team_dashboard(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    team_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get team-level dashboard metrics."""
    try:
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        params = {"start_date": start_date, "end_date": end_date}
        team_filter = ""

        if team_id:
            team_filter = " AND u.branch_id = :team_id"
            params["team_id"] = team_id

        # Get overall metrics
        metrics_sql = """
            SELECT
                COUNT(*) as total_calls,
                AVG(r.duration_seconds) as avg_duration,
                COUNT(CASE WHEN r.status = 'scored' THEN 1 END) as scored_calls
            FROM ci_call_recordings r
            JOIN users u ON u.id = r.agent_user_id
            WHERE r.created_at BETWEEN :start_date AND :end_date
        """ + team_filter
        metrics_result = db.execute(text(metrics_sql), params)

        metrics_row = metrics_result.fetchone()

        # Get QA score distribution
        score_sql = """
            SELECT
                AVG(s.percentage_score) as avg_score,
                COUNT(CASE WHEN s.grade = 'A' THEN 1 END) as grade_a,
                COUNT(CASE WHEN s.grade = 'B' THEN 1 END) as grade_b,
                COUNT(CASE WHEN s.grade = 'C' THEN 1 END) as grade_c,
                COUNT(CASE WHEN s.grade IN ('D', 'F') THEN 1 END) as grade_low
            FROM ci_qa_scorecards s
            JOIN ci_call_recordings r ON r.id = s.recording_id
            JOIN users u ON u.id = r.agent_user_id
            WHERE s.created_at BETWEEN :start_date AND :end_date
        """ + team_filter
        score_result = db.execute(text(score_sql), params)

        score_row = score_result.fetchone()

        # Get top performers
        performers_sql = """
            SELECT
                u.id, u.email, u.full_name,
                COUNT(r.id) as call_count,
                AVG(s.percentage_score) as avg_score
            FROM users u
            JOIN ci_call_recordings r ON r.agent_user_id = u.id
            LEFT JOIN ci_qa_scorecards s ON s.recording_id = r.id
            WHERE r.created_at BETWEEN :start_date AND :end_date
        """ + team_filter + """
            GROUP BY u.id, u.email, u.full_name
            ORDER BY avg_score DESC NULLS LAST
            LIMIT 5
        """
        performers_result = db.execute(text(performers_sql), params)

        top_performers = []
        for row in performers_result.fetchall():
            top_performers.append({
                "agent_id": row[0],
                "email": row[1],
                "name": row[2] or row[1],
                "call_count": row[3],
                "avg_score": round(float(row[4]), 1) if row[4] else None
            })

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "metrics": {
                "total_calls": metrics_row[0] or 0,
                "avg_duration_seconds": round(float(metrics_row[1] or 0), 0),
                "scored_calls": metrics_row[2] or 0
            },
            "qa_summary": {
                "avg_score": round(float(score_row[0] or 0), 1),
                "grade_distribution": {
                    "A": score_row[1] or 0,
                    "B": score_row[2] or 0,
                    "C": score_row[3] or 0,
                    "D/F": score_row[4] or 0
                }
            },
            "top_performers": top_performers
        }

    except Exception as e:
        logger.error(f"Error getting team dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboard/agent/{agent_id}")
async def get_agent_dashboard(
    agent_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get individual agent dashboard metrics."""
    try:
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        params = {
            "agent_id": agent_id,
            "start_date": start_date,
            "end_date": end_date
        }

        # Get agent metrics
        metrics_result = db.execute(text("""
            SELECT
                COUNT(*) as total_calls,
                AVG(r.duration_seconds) as avg_duration,
                SUM(r.duration_seconds) as total_duration,
                COUNT(CASE WHEN r.status = 'scored' THEN 1 END) as scored_calls
            FROM ci_call_recordings r
            WHERE r.agent_user_id = :agent_id
            AND r.created_at BETWEEN :start_date AND :end_date
        """), params)

        metrics_row = metrics_result.fetchone()

        # Get QA scores
        scores_result = db.execute(text("""
            SELECT
                AVG(s.percentage_score) as avg_score,
                MIN(s.percentage_score) as min_score,
                MAX(s.percentage_score) as max_score,
                s.grade,
                COUNT(*) as count
            FROM ci_qa_scorecards s
            JOIN ci_call_recordings r ON r.id = s.recording_id
            WHERE r.agent_user_id = :agent_id
            AND s.created_at BETWEEN :start_date AND :end_date
            GROUP BY s.grade
            ORDER BY count DESC
        """), params)

        grade_dist = {}
        avg_score = 0
        for row in scores_result.fetchall():
            if row[0]:
                avg_score = float(row[0])
            grade_dist[row[3]] = row[4]

        # Get recent recordings
        recent_result = db.execute(text("""
            SELECT r.id, r.direction, r.duration_seconds, r.status,
                   r.created_at, s.grade, s.percentage_score
            FROM ci_call_recordings r
            LEFT JOIN ci_qa_scorecards s ON s.recording_id = r.id
            WHERE r.agent_user_id = :agent_id
            ORDER BY r.created_at DESC
            LIMIT 10
        """), {"agent_id": agent_id})

        recent_calls = []
        for row in recent_result.fetchall():
            created_at = row[4]
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            recent_calls.append({
                "id": str(row[0]),
                "direction": row[1],
                "duration_seconds": row[2],
                "status": row[3],
                "created_at": created_at,
                "qa_grade": row[5],
                "qa_score": float(row[6]) if row[6] else None
            })

        # Get pending assignments
        assignments_result = db.execute(text("""
            SELECT COUNT(*) FROM ci_coaching_assignments
            WHERE agent_user_id = :agent_id AND status = 'pending'
        """), {"agent_id": agent_id})

        pending_assignments = assignments_result.fetchone()[0]

        return {
            "agent_id": agent_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "metrics": {
                "total_calls": metrics_row[0] or 0,
                "avg_duration_seconds": round(float(metrics_row[1] or 0), 0),
                "total_talk_time_hours": round(float(metrics_row[2] or 0) / 3600, 1),
                "scored_calls": metrics_row[3] or 0
            },
            "qa_summary": {
                "avg_score": round(avg_score, 1),
                "grade_distribution": grade_dist
            },
            "recent_calls": recent_calls,
            "pending_assignments": pending_assignments
        }

    except Exception as e:
        logger.error(f"Error getting agent dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboard/compliance")
async def get_compliance_dashboard(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get compliance monitoring dashboard."""
    try:
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        params = {"start_date": start_date, "end_date": end_date}

        # Get violation summary
        violations_result = db.execute(text("""
            SELECT
                v.rule_id, r.name as rule_name, r.severity,
                COUNT(*) as violation_count
            FROM ci_compliance_violations v
            JOIN ci_compliance_rules r ON r.id = v.rule_id
            WHERE v.detected_at BETWEEN :start_date AND :end_date
            GROUP BY v.rule_id, r.name, r.severity
            ORDER BY violation_count DESC
        """), params)

        violations_by_rule = []
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for row in violations_result.fetchall():
            violations_by_rule.append({
                "rule_id": str(row[0]),
                "rule_name": row[1],
                "severity": row[2],
                "count": row[3]
            })
            severity_counts[row[2]] = severity_counts.get(row[2], 0) + row[3]

        # Get recent violations
        recent_result = db.execute(text("""
            SELECT v.id, v.recording_id, r.name as rule_name,
                   r.severity, v.detected_at, v.reviewed
            FROM ci_compliance_violations v
            JOIN ci_compliance_rules r ON r.id = v.rule_id
            WHERE v.detected_at BETWEEN :start_date AND :end_date
            ORDER BY v.detected_at DESC
            LIMIT 20
        """), params)

        recent_violations = []
        for row in recent_result.fetchall():
            recent_violations.append({
                "id": str(row[0]),
                "recording_id": str(row[1]),
                "rule_name": row[2],
                "severity": row[3],
                "detected_at": row[4].isoformat() if row[4] else None,
                "reviewed": row[5]
            })

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "severity_summary": severity_counts,
            "total_violations": sum(severity_counts.values()),
            "violations_by_rule": violations_by_rule,
            "recent_violations": recent_violations
        }

    except Exception as e:
        logger.error(f"Error getting compliance dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

@router.get("/export/recordings")
async def export_recordings(
    request: Request,
    format: str = Query(default="csv", description="csv or json"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    agent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Export recordings data."""
    try:
        filters = ["1=1"]
        params = {}

        if start_date:
            filters.append("r.created_at >= :start_date")
            params["start_date"] = start_date
        if end_date:
            filters.append("r.created_at <= :end_date")
            params["end_date"] = end_date
        if agent_id:
            filters.append("r.agent_user_id = :agent_id")
            params["agent_user_id"] = agent_id

        where_clause = " AND ".join(filters)

        sql = """
            SELECT r.id, r.agent_user_id, u.email as agent_email,
                   r.direction, r.duration_seconds, r.status,
                   r.created_at, s.grade, s.percentage_score
            FROM ci_call_recordings r
            LEFT JOIN users u ON u.id = r.agent_user_id
            LEFT JOIN ci_qa_scorecards s ON s.recording_id = r.id
            WHERE """ + where_clause + """
            ORDER BY r.created_at DESC
        """
        result = db.execute(text(sql), params)

        rows = result.fetchall()

        if format == "json":
            data = []
            for row in rows:
                data.append({
                    "id": str(row[0]),
                    "agent_id": row[1],
                    "agent_email": row[2],
                    "direction": row[3],
                    "duration_seconds": row[4],
                    "status": row[5],
                    "created_at": row[6].isoformat() if row[6] else None,
                    "qa_grade": row[7],
                    "qa_score": float(row[8]) if row[8] else None
                })
            try:
                from utils.export_audit import log_export_event, _get_client_ip
                user_id = current_user.get("id", 0) if isinstance(current_user, dict) else getattr(current_user, "id", 0)
                org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
                log_export_event(
                    db=db, user_id=user_id, organization_id=org_id,
                    resource_type="call_recordings", export_format="json",
                    ip_address=_get_client_ip(request),
                    details={"record_count": len(data)},
                )
            except Exception:
                pass
            return {"recordings": data, "count": len(data)}

        else:  # CSV
            import csv
            import io

            def _sanitize_csv(val):
                """Prevent CSV formula injection by prefixing dangerous characters."""
                s = str(val) if val is not None else ""
                if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
                    return "'" + s
                return s

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ID", "Agent ID", "Agent Email", "Direction",
                "Duration (s)", "Status", "Created At", "QA Grade", "QA Score"
            ])

            for row in rows:
                writer.writerow([
                    str(row[0]), _sanitize_csv(row[1]), _sanitize_csv(row[2]), _sanitize_csv(row[3]),
                    row[4], _sanitize_csv(row[5]),
                    row[6].isoformat() if row[6] else "",
                    _sanitize_csv(row[7] or ""), row[8] or ""
                ])

            output.seek(0)

            try:
                from utils.export_audit import log_export_event, _get_client_ip
                user_id = current_user.get("id", 0) if isinstance(current_user, dict) else getattr(current_user, "id", 0)
                org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
                log_export_event(
                    db=db, user_id=user_id, organization_id=org_id,
                    resource_type="call_recordings", export_format="csv",
                    ip_address=_get_client_ip(request),
                    details={"record_count": len(rows)},
                )
            except Exception:
                pass

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=recordings_export.csv"
                }
            )

    except Exception as e:
        logger.error(f"Error exporting recordings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ci-voice",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/diagnostic/rubrics")
async def diagnostic_rubrics(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Diagnostic endpoint to check rubrics data."""
    try:
        result = db.execute(text("""
            SELECT COUNT(*) as count FROM ci_qa_rubrics WHERE is_active = true
        """))
        count = result.scalar() or 0

        # Get sample rubrics
        samples = db.execute(text("""
            SELECT id, name, category FROM ci_qa_rubrics
            WHERE is_active = true LIMIT 5
        """))
        sample_list = [{"id": str(r[0]), "name": r[1], "category": r[2]} for r in samples.fetchall()]

        return {
            "status": "ok",
            "rubrics_count": count,
            "samples": sample_list
        }
    except SQLAlchemyError as e:
        return {
            "status": "error",
            "error": "Internal server error",
            "rubrics_count": 0
        }


# =============================================================================
# AUTOMATED CALL SUMMARY ENDPOINTS
# =============================================================================

class SummaryGenerateRequest(BaseModel):
    """Request to generate call summary."""
    summary_type: str = Field(default="standard", description="quick, standard, executive, or coaching")
    auto_create_tasks: bool = True


class SummaryResponse(BaseModel):
    """Response for call summary."""
    recording_id: str
    summary_type: str
    one_liner: str
    executive_summary: str
    key_points: List[str]
    call_outcome: str
    customer_sentiment: str
    insights: List[Dict[str, Any]]
    follow_up_tasks: List[Dict[str, Any]]
    generated_at: str


@router.post("/recordings/{recording_id}/summary", response_model=SummaryResponse)
async def generate_call_summary(
    recording_id: str,
    request: SummaryGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an AI-powered summary for a call recording.

    Summary types:
    - quick: 30-second read, 3-5 bullets
    - standard: Full analysis with action items
    - executive: Manager-focused with metrics
    - coaching: Training-focused with improvement areas
    """
    try:
        from services.call_summary_service import CallSummaryService, SummaryType

        service = CallSummaryService(db)

        # Map string to enum
        type_map = {
            "quick": SummaryType.QUICK,
            "standard": SummaryType.STANDARD,
            "executive": SummaryType.EXECUTIVE,
            "coaching": SummaryType.COACHING
        }
        summary_type = type_map.get(request.summary_type, SummaryType.STANDARD)

        # Generate summary
        summary = await service.generate_summary(
            recording_id=recording_id,
            summary_type=summary_type,
            auto_create_tasks=request.auto_create_tasks
        )

        return SummaryResponse(
            recording_id=summary.recording_id,
            summary_type=summary.summary_type,
            one_liner=summary.one_liner,
            executive_summary=summary.executive_summary,
            key_points=summary.key_points,
            call_outcome=summary.call_outcome,
            customer_sentiment=summary.customer_sentiment,
            insights=[i.__dict__ if hasattr(i, '__dict__') else i for i in summary.insights],
            follow_up_tasks=[t.__dict__ if hasattr(t, '__dict__') else t for t in summary.follow_up_tasks],
            generated_at=summary.generated_at
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/recordings/{recording_id}/summary")
async def get_call_summary(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get existing summary for a recording."""
    try:
        from services.call_summary_service import CallSummaryService

        service = CallSummaryService(db)
        summary = service.get_summary(recording_id)

        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found")

        return summary.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summaries/recent")
async def get_recent_summaries(
    agent_id: Optional[int] = None,
    days: int = Query(default=7, le=90),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get recent call summaries with filters."""
    try:
        from services.call_summary_service import CallSummaryService

        service = CallSummaryService(db)
        summaries = service.get_recent_summaries(
            agent_id=agent_id,
            days=days,
            limit=limit
        )

        return {
            "summaries": summaries,
            "count": len(summaries),
            "filters": {
                "agent_id": agent_id,
                "days": days
            }
        }

    except Exception as e:
        logger.error(f"Error getting recent summaries: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summaries/stats")
async def get_summary_statistics(
    agent_id: Optional[int] = None,
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get aggregate summary statistics."""
    try:
        from services.call_summary_service import CallSummaryService

        service = CallSummaryService(db)
        stats = service.get_summary_stats(agent_id=agent_id, days=days)

        return {
            "period_days": days,
            "agent_id": agent_id,
            **stats
        }

    except Exception as e:
        logger.error(f"Error getting summary stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/summaries/process-pending")
async def process_pending_summaries(
    limit: int = Query(default=50, le=200),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Process all recordings that don't have summaries yet.
    Useful for batch processing or catching up on missed calls.
    """
    try:
        from services.call_summary_service import CallSummaryService

        service = CallSummaryService(db)
        result = await service.process_pending_summaries(limit=limit)

        return {
            "status": "completed",
            **result
        }

    except Exception as e:
        logger.error(f"Error processing pending summaries: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summaries/feed")
async def get_summary_feed(
    team_id: Optional[int] = None,
    outcome: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a feed of call summaries for the dashboard.
    Shows the most recent calls with one-liner summaries.
    """
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if team_id:
            filters.append("u.branch_id = :team_id")
            params["team_id"] = team_id
        if outcome:
            filters.append("s.call_outcome = :outcome")
            params["outcome"] = outcome
        if sentiment:
            filters.append("s.customer_sentiment = :sentiment")
            params["sentiment"] = sentiment

        where_clause = " AND ".join(filters)

        sql = """
            SELECT
                s.id, s.recording_id, s.one_liner, s.call_outcome,
                s.customer_sentiment, s.customer_urgency, s.generated_at,
                r.direction, r.duration_seconds,
                u.id as agent_id, u.full_name as agent_name,
                COALESCE(l.borrower_name, ld.first_name || ' ' || ld.last_name) as customer_name
            FROM ci_call_summaries s
            JOIN ci_call_recordings r ON r.id = s.recording_id
            LEFT JOIN users u ON u.id = r.agent_user_id
            LEFT JOIN loans l ON l.id = s.loan_id
            LEFT JOIN leads ld ON ld.id = s.lead_id
            WHERE """ + where_clause + """
            ORDER BY s.generated_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), params)

        feed = []
        for row in result.fetchall():
            generated_at = row[6]
            if generated_at and hasattr(generated_at, 'isoformat'):
                generated_at = generated_at.isoformat()

            feed.append({
                "id": str(row[0]),
                "recording_id": str(row[1]),
                "one_liner": row[2],
                "call_outcome": row[3],
                "customer_sentiment": row[4],
                "customer_urgency": row[5],
                "generated_at": generated_at,
                "direction": row[7],
                "duration_seconds": row[8],
                "agent": {
                    "id": row[9],
                    "name": row[10]
                },
                "customer_name": row[11]
            })

        return {
            "feed": feed,
            "count": len(feed),
            "offset": offset,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"Error getting summary feed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
