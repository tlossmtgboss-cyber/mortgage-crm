"""
UVIP - Video Meeting Recording Routes
Extracted from video_meeting_routes.py

Handles:
- Recording start/stop
- Screen recording upload/download/delete
- Recording transcript and analysis
- Recording reprocessing
- Twilio conference and recording callbacks
- Recording consent endpoints
- Transcription endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, File, UploadFile, Form
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pathlib import Path
import logging
import os
import uuid
import re
import secrets

from video_meeting_shared import (
    get_db, get_current_user, get_models,
    verify_room_access, verify_recording_access,
    process_recording, process_recording_ai, _validate_twilio_signature,
)
from video_meeting_schemas import (
    StartRecordingRequest, RecordingConsentRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Storage for screen recordings (in production, use S3 or similar)
SCREEN_RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "screen_recordings")
os.makedirs(SCREEN_RECORDINGS_DIR, exist_ok=True)

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_RECORDING_EXTENSIONS = {"webm", "mp4", "mkv"}
UPLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB


# ============================================================================
# SCREEN RECORDING ENDPOINTS
# ============================================================================

@router.post("/screen-recordings/upload")
async def upload_screen_recording(
    request: Request,
    file: UploadFile = File(...),
    meeting_id: Optional[str] = Form(None),
    room_code: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Upload a screen recording and return a shareable link."""
    try:
        file_ext = Path(file.filename).suffix.lower().lstrip('.') if file.filename else ''
        if not file_ext:
            file_ext = 'webm'
        if file_ext not in ALLOWED_RECORDING_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '.{file_ext}'. Allowed: {', '.join(ALLOWED_RECORDING_EXTENSIONS)}"
            )

        recording_id = str(uuid.uuid4())
        filename = f"{recording_id}.{file_ext}"
        filepath = Path(SCREEN_RECORDINGS_DIR).resolve() / filename
        if not str(filepath).startswith(str(Path(SCREEN_RECORDINGS_DIR).resolve())):
            raise HTTPException(status_code=400, detail="Invalid file path")
        filepath = str(filepath)

        total_size = 0
        try:
            with open(filepath, 'wb') as f:
                while True:
                    chunk = await file.read(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_UPLOAD_SIZE:
                        break
                    f.write(chunk)
        except Exception as e:
            logger.exception(f"Failed to write uploaded file to disk: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            raise

        if total_size > MAX_UPLOAD_SIZE:
            if os.path.exists(filepath):
                os.remove(filepath)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB"
            )

        base_url = os.getenv('BACKEND_URL', str(request.base_url).rstrip('/'))
        share_url = f"{base_url}/api/v1/meetings/screen-recordings/{recording_id}"

        logger.info(f"Screen recording uploaded: {recording_id} by user {current_user.id}, meeting: {meeting_id or room_code}, size: {total_size}")

        return {
            "success": True,
            "recording_id": recording_id,
            "share_url": share_url,
            "filename": filename,
            "size_bytes": total_size
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading screen recording: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload recording")


@router.get("/screen-recordings/{recording_id}")
async def get_screen_recording(
    recording_id: str,
    current_user=Depends(get_current_user)
):
    """Retrieve a screen recording by ID (authenticated endpoint)."""
    from fastapi.responses import FileResponse

    if not re.match(r'^[a-zA-Z0-9\-]+$', recording_id):
        raise HTTPException(status_code=400, detail="Invalid recording ID")

    recordings_dir = Path(SCREEN_RECORDINGS_DIR).resolve()
    for ext in ALLOWED_RECORDING_EXTENSIONS:
        filepath = recordings_dir / f"{recording_id}.{ext}"
        if filepath.exists() and str(filepath).startswith(str(recordings_dir)):
            return FileResponse(
                str(filepath),
                media_type=f"video/{ext}",
                filename=f"screen-recording-{recording_id}.{ext}"
            )

    raise HTTPException(status_code=404, detail="Recording not found")


@router.delete("/screen-recordings/{recording_id}")
async def delete_screen_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete a screen recording."""
    recordings_dir = Path(SCREEN_RECORDINGS_DIR).resolve()
    for ext in ALLOWED_RECORDING_EXTENSIONS:
        filepath = recordings_dir / f"{recording_id}.{ext}"
        if filepath.exists() and str(filepath).startswith(str(recordings_dir)):
            filepath.unlink()
            return {"success": True, "message": "Recording deleted"}

    raise HTTPException(status_code=404, detail="Recording not found")


# ============================================================================
# RECORDING ENDPOINTS
# ============================================================================

@router.get("/rooms/{room_id}/recordings")
async def list_recordings(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List all recordings for a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")
    if not verify_room_access(room, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    if MeetingRecording is None:
        return {"recordings": []}

    recordings = db.query(MeetingRecording).filter(
        MeetingRecording.meeting_id == room_id,
        MeetingRecording.is_deleted == False
    ).all()

    return {
        "recordings": [
            {
                "id": r.id,
                "recording_uuid": r.recording_uuid,
                "recording_name": r.recording_name,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "file_size_bytes": r.file_size_bytes,
                "video_format": r.video_format,
                "transcription_requested": r.transcription_requested,
                "download_count": r.download_count,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in recordings
        ]
    }


@router.post("/rooms/{room_id}/recordings/start")
async def start_recording(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Start recording a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start recording")

    if not room.recording_enabled:
        raise HTTPException(status_code=400, detail="Recording is not enabled for this meeting")

    recording = MeetingRecording(
        meeting_id=room_id,
        recording_uuid=secrets.token_urlsafe(16),
        recording_name=f"{room.room_name} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        status="recording",
        recording_started_at=datetime.utcnow(),
        transcription_requested=room.transcription_enabled,
        created_by=current_user.id
    )

    db.add(recording)
    db.commit()
    db.refresh(recording)

    return {"success": True, "recording": {"id": recording.id, "recording_uuid": recording.recording_uuid, "status": recording.status}}


@router.post("/rooms/{room_id}/recordings/{recording_id}/stop")
async def stop_recording(
    room_id: int,
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Stop recording a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can stop recording")

    recording = db.query(MeetingRecording).filter(
        MeetingRecording.id == recording_id,
        MeetingRecording.meeting_id == room_id
    ).first()

    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    recording.status = "processing"
    recording.recording_ended_at = datetime.utcnow()
    recording.processing_started_at = datetime.utcnow()

    if recording.recording_started_at:
        recording.duration_seconds = int((recording.recording_ended_at - recording.recording_started_at).total_seconds())

    db.commit()

    background_tasks.add_task(process_recording, recording_id)

    return {"success": True, "recording": {"id": recording.id, "status": recording.status, "duration_seconds": recording.duration_seconds}}


# ============================================================================
# RECORDING TRANSCRIPT & ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/transcript")
async def get_recording_transcript(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get transcript for a recording."""
    _models = get_models()

    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    RecordingTranscript = _models.get('RecordingTranscript')
    if RecordingTranscript is None:
        return {"error": "Transcripts not available"}

    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id
    ).first()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return {
        "transcript_id": transcript.id,
        "recording_id": transcript.recording_id,
        "status": transcript.status,
        "full_transcript": transcript.full_transcript,
        "segments": transcript.transcript_json or [],
        "language": transcript.language,
        "word_count": transcript.word_count,
        "speakers_detected": transcript.speakers_detected,
        "speaker_mapping": transcript.speaker_mapping
    }


@router.get("/recordings/{recording_id}/analysis")
async def get_recording_analysis(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get AI analysis for a recording."""
    _models = get_models()

    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    MeetingAIAnalysis = _models.get('MeetingAIAnalysis')
    if MeetingAIAnalysis is None:
        return {"error": "Analysis not available"}

    analysis = db.query(MeetingAIAnalysis).filter(
        MeetingAIAnalysis.recording_id == recording_id
    ).first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    structured = analysis.structured_content or {}

    return {
        "analysis_id": analysis.id,
        "recording_id": analysis.recording_id,
        "status": analysis.status,
        "summary": analysis.content or structured.get("summary"),
        "key_topics": structured.get("key_topics", []),
        "action_items": structured.get("action_items", []),
        "decisions_made": structured.get("decisions_made", []),
        "questions_discussed": structured.get("questions_discussed", []),
        "sentiment": structured.get("sentiment", {}),
        "engagement_metrics": structured.get("engagement_metrics", {}),
        "mortgage_insights": structured.get("mortgage_insights", {}),
        "compliance_notes": structured.get("compliance_notes", []),
        "follow_up_recommendations": structured.get("follow_up_recommendations", [])
    }


@router.post("/recordings/{recording_id}/reprocess")
async def reprocess_recording(
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Reprocess a recording for AI analysis."""
    _models = get_models()
    MeetingRecording = _models.get('MeetingRecording')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    recording.status = "processing"
    db.commit()

    background_tasks.add_task(
        process_recording_ai,
        recording.id,
        recording.meeting_id,
        True
    )

    return {"success": True, "status": "reprocessing"}


# ============================================================================
# TWILIO CONFERENCE & RECORDING CALLBACKS
# ============================================================================

@router.post("/twilio/connect/{room_code}")
async def twilio_connect_to_meeting(
    room_code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """TwiML endpoint for connecting participant to meeting conference."""
    from fastapi.responses import Response

    if not await _validate_twilio_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        from uvip.recording_service import get_recording_service
        recording_service = get_recording_service()

        form_data = await request.form()
        caller = form_data.get("Caller", "Unknown")
        caller_name = form_data.get("CallerName", caller)

        twiml = recording_service.get_conference_twiml(
            meeting_room_id=room_code,
            participant_name=caller_name,
            is_host=False
        )

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Twilio connect error: {e}")
        from twilio.twiml.voice_response import VoiceResponse
        response = VoiceResponse()
        response.say("Sorry, there was an error connecting to the meeting. Please try again.")
        return Response(content=str(response), media_type="application/xml")


@router.post("/twilio/recording-callback/{room_code}")
async def twilio_recording_callback(
    room_code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Handle Twilio recording completion callback."""
    if not await _validate_twilio_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    try:
        form_data = await request.form()

        recording_sid = form_data.get("RecordingSid")
        recording_url = form_data.get("RecordingUrl")
        recording_duration = int(form_data.get("RecordingDuration", 0))
        recording_status = form_data.get("RecordingStatus")

        logger.info(f"Recording callback for {room_code}: SID={recording_sid}, Status={recording_status}")

        if recording_status != "completed":
            return {"status": "acknowledged", "recording_status": recording_status}

        room = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.room_code == room_code
        ).first()

        if not room:
            logger.error(f"Meeting room {room_code} not found for recording callback")
            return {"error": "Meeting not found"}

        recording = MeetingRecording(
            meeting_id=room.id,
            recording_uuid=recording_sid,
            recording_name=f"{room.room_name} - Recording",
            storage_provider="twilio",
            storage_path=recording_url,
            duration_seconds=recording_duration,
            audio_format="mp3",
            status="processing",
            recording_started_at=room.actual_start,
            recording_ended_at=datetime.utcnow(),
            transcription_requested=room.transcription_enabled,
            created_by=room.host_user_id
        )

        db.add(recording)
        db.commit()
        db.refresh(recording)

        background_tasks.add_task(
            process_recording_ai,
            recording.id,
            room.id,
            room.transcription_enabled
        )

        return {
            "success": True,
            "recording_id": recording.id,
            "status": "processing"
        }

    except Exception as e:
        logger.error(f"Recording callback error: {e}")
        return {"error": "Internal processing error"}


@router.post("/twilio/call-status/{room_code}")
async def twilio_call_status_callback(
    room_code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Twilio call status updates."""
    if not await _validate_twilio_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        form_data = await request.form()

        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")

        logger.info(f"Call status update for {room_code}: SID={call_sid}, Status={call_status}")

        _models = get_models()
        MeetingParticipant = _models.get('MeetingParticipant')
        VideoMeetingRoom = _models.get('VideoMeetingRoom')

        room = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.room_code == room_code
        ).first()

        if room and MeetingParticipant:
            pass

        return {"status": "acknowledged"}

    except Exception as e:
        logger.error(f"Call status callback error: {e}")
        return {"error": "Internal processing error"}


# ============================================================================
# RECORDING CONSENT ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/recordings/start-with-consent")
async def start_recording_with_consent(
    room_id: int,
    data: StartRecordingRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Start recording with consent metadata tracked."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start recording")

    if not room.recording_enabled:
        raise HTTPException(status_code=400, detail="Recording is not enabled for this meeting")

    if data.consent_type == "all_party" and MeetingParticipant:
        active_participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id,
            MeetingParticipant.status == "joined"
        ).all()

        not_consented = [
            {"id": p.id, "display_name": p.display_name, "email": p.email}
            for p in active_participants
            if not p.recording_consent_given and p.user_id != current_user.id
        ]

        if not_consented:
            return {
                "success": False,
                "error": "all_party_consent_required",
                "message": "All participants must consent before recording in an all-party consent state",
                "pending_consent": not_consented
            }

    recording = MeetingRecording(
        meeting_id=room_id,
        recording_uuid=secrets.token_urlsafe(16),
        recording_name=f"{room.room_name} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        status="recording",
        recording_started_at=datetime.utcnow(),
        transcription_requested=room.transcription_enabled,
        created_by=current_user.id,
        consent_obtained=True,
        consent_type=data.consent_type,
        consent_state_code=data.state_code,
        disclosure_script_shown=data.disclosure_script,
        consent_obtained_at=datetime.utcnow()
    )

    db.add(recording)
    db.commit()
    db.refresh(recording)

    return {
        "success": True,
        "recording": {
            "id": recording.id,
            "recording_uuid": recording.recording_uuid,
            "status": recording.status,
            "consent_type": data.consent_type,
            "consent_state_code": data.state_code
        }
    }


@router.post("/rooms/{room_id}/recordings/{recording_id}/consent")
async def submit_recording_consent(
    room_id: int,
    recording_id: int,
    data: RecordingConsentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Submit recording consent for a participant."""
    _models = get_models()
    MeetingParticipant = _models.get('MeetingParticipant')

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        MeetingParticipant.user_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.recording_consent_given = data.consent_given
    participant.recording_consent_at = datetime.utcnow()
    participant.recording_consent_method = data.method

    db.commit()

    return {
        "success": True,
        "consent_given": data.consent_given,
        "method": data.method
    }


@router.get("/rooms/{room_id}/recordings/consent-status")
async def get_consent_status(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get recording consent status for all active participants in a meeting."""
    _models = get_models()
    MeetingParticipant = _models.get('MeetingParticipant')

    participants = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        MeetingParticipant.status == "joined"
    ).all()

    return {
        "room_id": room_id,
        "participants": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "display_name": p.display_name,
                "consent_given": p.recording_consent_given or False,
                "consent_at": p.recording_consent_at.isoformat() if p.recording_consent_at else None,
                "consent_method": p.recording_consent_method
            }
            for p in participants
        ],
        "all_consented": all(p.recording_consent_given for p in participants)
    }


# ============================================================================
# TRANSCRIPTION ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/recordings/{recording_id}/transcribe")
async def start_transcription(
    room_id: int,
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Start transcription of a meeting recording."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')
    RecordingTranscript = _models.get('RecordingTranscript')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    recording = db.query(MeetingRecording).filter(
        MeetingRecording.id == recording_id,
        MeetingRecording.meeting_id == room_id
    ).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    existing = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id
    ).first()
    if existing and existing.status in ("processing", "completed"):
        return {
            "success": True,
            "message": f"Transcript already {existing.status}",
            "transcript_id": existing.id,
            "status": existing.status
        }

    transcript = RecordingTranscript(
        recording_id=recording_id,
        meeting_id=room_id,
        status="pending"
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)

    return {
        "success": True,
        "transcript_id": transcript.id,
        "status": "pending",
        "message": "Transcription queued"
    }


@router.get("/rooms/{room_id}/recordings/{recording_id}/transcript")
async def get_transcript(
    room_id: int,
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get the transcript for a recording."""
    _models = get_models()
    RecordingTranscript = _models.get('RecordingTranscript')

    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id,
        RecordingTranscript.meeting_id == room_id
    ).first()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return {
        "transcript_id": transcript.id,
        "status": transcript.status,
        "full_text": transcript.full_transcript,
        "segments": transcript.transcript_json,
        "speakers_detected": transcript.speakers_detected,
        "word_count": transcript.word_count,
        "confidence": transcript.confidence_score,
        "provider": transcript.transcription_provider,
        "language": transcript.language
    }
