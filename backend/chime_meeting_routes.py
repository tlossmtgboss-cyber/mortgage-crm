"""
Chime Meeting Routes — Amazon Chime SDK-specific meeting operations.

Integrates with ChimeMeetingService for meeting lifecycle, attendee
management, server-side recording via media capture pipelines, and
live transcription via Amazon Transcribe.

Prefix: /api/v1/meetings/chime

Follows the same dependency injection pattern as video_meeting_shared.py:
    set_dependencies(get_db, get_current_user, models)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db_func = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db, get_current_user, models):
    """Set dependencies from main.py (same pattern as video_meeting_shared)."""
    global _get_db_func, _get_current_user_func, _models
    _get_db_func = get_db
    _get_current_user_func = get_current_user
    _models = models


def get_db():
    if _get_db_func is None:
        raise RuntimeError("Chime meeting routes: dependencies not set")
    yield from _get_db_func()


from auth.dependencies import get_current_user  # dedup: was local wrapper
def get_models():
    """Get the models dict. Raises RuntimeError if not initialized."""
    if _models is None:
        raise RuntimeError("Chime meeting routes: dependencies not set")
    return _models


def _get_chime_service():
    """Lazy-load ChimeMeetingService. Returns 503 if AWS creds not configured."""
    try:
        from services.chime_meeting_service import get_chime_service
        return get_chime_service()
    except Exception as e:
        logger.error(f"Failed to initialize Chime service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Chime meeting service is not available. AWS credentials may not be configured."
        )


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ChimeMeetingCreateRequest(BaseModel):
    room_name: str
    room_description: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: int = 30
    waiting_room_enabled: bool = True
    recording_enabled: bool = True
    transcription_enabled: bool = True
    ai_assistant_enabled: bool = True
    max_participants: int = 50
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    appointment_id: Optional[int] = None
    meeting_type: str = "general"


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/create")
async def create_chime_meeting(
    data: ChimeMeetingCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a Chime-backed meeting room.

    Creates a VideoMeetingRoom record with provider='chime', then provisions
    the Chime SDK meeting via AWS and stores the chime_meeting_id and
    chime_media_region on the room.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")
    MeetingParticipant = models.get("MeetingParticipant")

    if VideoMeetingRoom is None:
        raise HTTPException(status_code=500, detail="VideoMeetingRoom model not found")

    chime_service = _get_chime_service()

    # Generate room code
    from video_meeting_shared import generate_room_code
    from sqlalchemy.exc import IntegrityError

    max_attempts = 3
    room = None
    for attempt in range(max_attempts):
        room_code = generate_room_code()
        room = VideoMeetingRoom(
            room_code=room_code,
            room_name=data.room_name,
            room_description=data.room_description,
            provider="chime",
            host_user_id=current_user.id,
            organization_id=getattr(current_user, "organization_id", None),
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            duration_minutes=data.duration_minutes,
            status="scheduled" if data.scheduled_start else "active",
            waiting_room_enabled=data.waiting_room_enabled,
            recording_enabled=data.recording_enabled,
            transcription_enabled=data.transcription_enabled,
            ai_assistant_enabled=data.ai_assistant_enabled,
            max_participants=data.max_participants,
            loan_id=data.loan_id,
            lead_id=data.lead_id,
            appointment_id=data.appointment_id,
            meeting_type=data.meeting_type,
            created_by=current_user.id,
        )
        db.add(room)
        try:
            db.commit()
            db.refresh(room)
            break
        except IntegrityError:
            db.rollback()
            logger.warning(f"Room code collision on attempt {attempt + 1}: {room_code}")
            room = None
            if attempt == max_attempts - 1:
                raise HTTPException(status_code=500, detail="Failed to generate unique room code")

    # Create the Chime SDK meeting
    try:
        chime_meeting = chime_service.create_meeting(external_id=room.room_code)
        room.chime_meeting_id = chime_meeting["MeetingId"]
        room.chime_media_region = chime_meeting.get("MediaRegion")
        db.commit()
        db.refresh(room)
    except Exception as e:
        logger.error(f"Failed to create Chime meeting for room {room.room_code}: {e}")
        # Clean up the room record since Chime provisioning failed
        db.delete(room)
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="Failed to provision Chime meeting with AWS. Please try again."
        )

    # Add host as participant
    if MeetingParticipant:
        host_participant = MeetingParticipant(
            meeting_id=room.id,
            user_id=current_user.id,
            email=current_user.email,
            display_name=current_user.email.split("@")[0],
            role="host",
            status="invited",
        )
        db.add(host_participant)
        db.commit()

    return {
        "success": True,
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "provider": "chime",
            "status": room.status,
            "scheduled_start": room.scheduled_start.isoformat() if room.scheduled_start else None,
            "scheduled_end": room.scheduled_end.isoformat() if room.scheduled_end else None,
            "duration_minutes": room.duration_minutes,
            "join_url": f"/meeting/{room.room_code}",
            "host_url": f"/meeting/{room.room_code}?host=true",
        },
        "chime": {
            "meeting_id": chime_meeting["MeetingId"],
            "media_region": chime_meeting.get("MediaRegion"),
            "media_placement": chime_meeting.get("MediaPlacement"),
        },
    }


@router.post("/join/{room_code}")
async def join_chime_meeting(
    room_code: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Join a Chime meeting and get SDK credentials.

    Looks up the VideoMeetingRoom by room_code, creates a Chime attendee,
    and returns the meeting + attendee data that the frontend SDK needs
    (MeetingSessionConfiguration).
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")

    room = db.query(VideoMeetingRoom).filter(
        VideoMeetingRoom.room_code == room_code
    ).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if room.status in ("cancelled", "ended"):
        raise HTTPException(status_code=400, detail=f"This meeting has been {room.status}")

    if not room.chime_meeting_id:
        raise HTTPException(
            status_code=400,
            detail="This meeting does not have an active Chime session"
        )

    chime_service = _get_chime_service()

    # Create attendee for the current user
    try:
        attendee = chime_service.create_attendee(
            meeting_id=room.chime_meeting_id,
            external_user_id=str(current_user.id),
        )
    except Exception as e:
        logger.error(f"Failed to create Chime attendee for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to create meeting attendee with AWS"
        )

    # Get full join info (Meeting + Attendee objects for SDK init)
    try:
        join_info = chime_service.get_meeting_join_info(
            meeting_id=room.chime_meeting_id,
            attendee_id=attendee["AttendeeId"],
        )
    except Exception as e:
        logger.error(f"Failed to get Chime join info: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve meeting join information from AWS"
        )

    # Update participant record if MeetingParticipant model exists
    MeetingParticipant = models.get("MeetingParticipant")
    if MeetingParticipant:
        existing = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room.id,
            MeetingParticipant.user_id == current_user.id,
        ).first()
        if existing:
            existing.status = "joined"
            existing.joined_at = datetime.now(timezone.utc)
        else:
            participant = MeetingParticipant(
                meeting_id=room.id,
                user_id=current_user.id,
                email=current_user.email,
                display_name=current_user.email.split("@")[0],
                role="participant",
                status="joined",
                joined_at=datetime.now(timezone.utc),
            )
            db.add(participant)
        db.commit()

    return {
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "status": room.status,
            "host_user_id": room.host_user_id,
            "recording_enabled": room.recording_enabled,
        },
        "chime": {
            "meeting": join_info["Meeting"],
            "attendee": join_info["Attendee"],
        },
    }


@router.post("/{room_id}/recording/start")
async def start_chime_recording(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Start server-side recording via a Chime media capture pipeline.

    Only the host can start recording. Creates a MeetingRecording record
    with the chime_pipeline_id for later stop/status tracking.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")
    MeetingRecording = models.get("MeetingRecording")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start recording")

    if not room.chime_meeting_id:
        raise HTTPException(status_code=400, detail="No active Chime session for this meeting")

    chime_service = _get_chime_service()

    try:
        pipeline_id = chime_service.start_recording(
            meeting_id=room.chime_meeting_id,
            organization_id=current_user.organization_id,
        )
    except Exception as e:
        logger.error(f"Failed to start Chime recording for meeting {room_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to start recording with AWS"
        )

    # Create MeetingRecording record
    recording = None
    if MeetingRecording:
        recording = MeetingRecording(
            meeting_id=room.id,
            recording_name=f"Recording - {datetime.now(timezone.utc).strftime('%b %d, %H:%M')}",
            status="recording",
            chime_pipeline_id=pipeline_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)

    return {
        "success": True,
        "pipeline_id": pipeline_id,
        "recording_id": recording.id if recording else None,
        "message": "Recording started",
    }


@router.post("/{room_id}/recording/stop")
async def stop_chime_recording(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Stop an active Chime recording by deleting the media capture pipeline.

    Only the host can stop recording. Finds the active MeetingRecording
    with a chime_pipeline_id and stops it.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")
    MeetingRecording = models.get("MeetingRecording")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can stop recording")

    if not MeetingRecording:
        raise HTTPException(status_code=500, detail="MeetingRecording model not available")

    # Find the active recording with a pipeline
    recording = db.query(MeetingRecording).filter(
        MeetingRecording.meeting_id == room.id,
        MeetingRecording.chime_pipeline_id.isnot(None),
        MeetingRecording.status == "recording",
    ).order_by(MeetingRecording.id.desc()).first()

    if not recording:
        raise HTTPException(status_code=404, detail="No active recording found for this meeting")

    chime_service = _get_chime_service()

    try:
        stopped = chime_service.stop_recording(pipeline_id=recording.chime_pipeline_id)
    except Exception as e:
        logger.error(f"Failed to stop Chime recording pipeline {recording.chime_pipeline_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to stop recording with AWS"
        )

    recording.status = "processing" if stopped else "error"
    recording.ended_at = datetime.now(timezone.utc)

    # Build the expected S3 key based on Chime media pipeline conventions
    # TENANT-011: Prefix with org_id for multi-tenant S3 isolation
    if stopped and room.chime_meeting_id:
        _org_id = getattr(current_user, "organization_id", None) or "unscoped"
        recording.s3_key = f"org_{_org_id}/meetings/{room.chime_meeting_id}/{recording.chime_pipeline_id}"

    db.commit()

    return {
        "success": stopped,
        "recording_id": recording.id,
        "status": recording.status,
        "message": "Recording stopped" if stopped else "Failed to stop recording",
    }


@router.post("/{room_id}/transcription/start")
async def start_chime_transcription(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Start live transcription for a Chime meeting using Amazon Transcribe.

    Only the host can enable transcription. Transcription events are
    delivered to the frontend via the Chime SDK data messages channel.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start transcription")

    if not room.chime_meeting_id:
        raise HTTPException(status_code=400, detail="No active Chime session for this meeting")

    chime_service = _get_chime_service()

    try:
        started = chime_service.start_transcription(meeting_id=room.chime_meeting_id)
    except Exception as e:
        logger.error(f"Failed to start transcription for meeting {room_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to start transcription with AWS"
        )

    if not started:
        raise HTTPException(status_code=502, detail="Transcription failed to start")

    return {
        "success": True,
        "message": "Live transcription started",
    }


@router.post("/{room_id}/transcription/stop")
async def stop_chime_transcription(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Stop live transcription for a Chime meeting.

    Only the host can disable transcription.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can stop transcription")

    if not room.chime_meeting_id:
        raise HTTPException(status_code=400, detail="No active Chime session for this meeting")

    chime_service = _get_chime_service()

    try:
        stopped = chime_service.stop_transcription(meeting_id=room.chime_meeting_id)
    except Exception as e:
        logger.error(f"Failed to stop transcription for meeting {room_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to stop transcription with AWS"
        )

    return {
        "success": stopped,
        "message": "Transcription stopped" if stopped else "Failed to stop transcription",
    }


@router.delete("/{room_id}")
async def end_chime_meeting(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    End a Chime meeting by deleting it from AWS and updating the room status.

    Only the host can end the meeting. This will disconnect all attendees.
    """
    models = get_models()
    VideoMeetingRoom = models.get("VideoMeetingRoom")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can end this meeting")

    # Delete the Chime meeting from AWS (disconnects all attendees)
    if room.chime_meeting_id:
        chime_service = _get_chime_service()
        try:
            chime_service.delete_meeting(meeting_id=room.chime_meeting_id)
        except Exception as e:
            logger.error(f"Failed to delete Chime meeting {room.chime_meeting_id}: {e}")
            # Continue with local status update even if AWS delete fails --
            # the meeting will eventually be cleaned up by Chime's TTL.

    room.status = "ended"
    room.actual_end = datetime.now(timezone.utc)
    room.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "status": room.status,
            "actual_end": room.actual_end.isoformat(),
        },
        "message": "Meeting ended",
    }


@router.get("/recording/{recording_id}/url")
async def get_recording_download_url(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get a presigned S3 download URL for a Chime recording.

    Validates the user has access to the parent meeting room before
    generating the URL.
    """
    models = get_models()
    MeetingRecording = models.get("MeetingRecording")
    VideoMeetingRoom = models.get("VideoMeetingRoom")

    if not MeetingRecording:
        raise HTTPException(status_code=500, detail="MeetingRecording model not available")

    recording = db.query(MeetingRecording).filter(
        MeetingRecording.id == recording_id
    ).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Validate access via the parent meeting room
    room = db.query(VideoMeetingRoom).filter(
        VideoMeetingRoom.id == recording.meeting_id
    ).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Check user has access: host, same org, or participant
    user_org = getattr(current_user, "organization_id", None)
    if room.host_user_id != current_user.id:
        if not (user_org and room.organization_id and user_org == room.organization_id):
            MeetingParticipant = models.get("MeetingParticipant")
            is_participant = False
            if MeetingParticipant:
                is_participant = db.query(MeetingParticipant).filter(
                    MeetingParticipant.meeting_id == room.id,
                    MeetingParticipant.user_id == current_user.id,
                ).first() is not None
            if not is_participant:
                raise HTTPException(status_code=403, detail="Access denied")

    if not recording.s3_key:
        raise HTTPException(
            status_code=404,
            detail="Recording file not yet available. It may still be processing."
        )

    chime_service = _get_chime_service()

    try:
        url = chime_service.get_presigned_url(s3_key=recording.s3_key)
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for recording {recording_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to generate download URL"
        )

    return {
        "success": True,
        "recording_id": recording_id,
        "download_url": url,
        "expires_in_seconds": 3600,
    }
