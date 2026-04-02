"""
UVIP - Video Meeting CRUD Routes
Extracted from video_meeting_routes.py

Handles:
- Meeting room CRUD (list, create, get, update, delete, start, end)
- Participant management (add, update, remove)
- Waiting room endpoints
- Meeting invite emails
- Instant meetings, join by code
- Dashboard stats, CRM linking
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, time
from typing import Optional
import logging
import os

from video_meeting_shared import (
    get_db, get_current_user, get_models, get_pwd_context,
    generate_room_code, _require_admin, _check_rate_limit,
    verify_room_access, verify_host_permission,
    process_meeting_ai_analysis, send_meeting_invite_email,
)
from video_meeting_schemas import (
    MeetingRoomCreate, MeetingRoomUpdate,
    ParticipantAdd, ParticipantUpdate,
    MeetingInviteRequest, WaitingRoomRequest, AdmitParticipantRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# MEETING ROOM ENDPOINTS
# ============================================================================

@router.get("/rooms")
async def list_meeting_rooms(
    status: Optional[str] = None,
    meeting_type: Optional[str] = None,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    start_date=None,
    end_date=None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List all meeting rooms for the current user."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    if VideoMeetingRoom is None:
        raise HTTPException(status_code=500, detail="VideoMeetingRoom model not found")

    query = db.query(VideoMeetingRoom).filter(
        or_(
            VideoMeetingRoom.host_user_id == current_user.id,
            VideoMeetingRoom.organization_id == getattr(current_user, 'organization_id', None)
        )
    )

    if status:
        query = query.filter(VideoMeetingRoom.status == status)
    if meeting_type:
        query = query.filter(VideoMeetingRoom.meeting_type == meeting_type)
    if loan_id:
        query = query.filter(VideoMeetingRoom.loan_id == loan_id)
    if lead_id:
        query = query.filter(VideoMeetingRoom.lead_id == lead_id)
    if start_date:
        query = query.filter(VideoMeetingRoom.scheduled_start >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(VideoMeetingRoom.scheduled_start <= datetime.combine(end_date, time.max))

    total = query.count()
    rooms = query.order_by(VideoMeetingRoom.scheduled_start.desc()).offset(offset).limit(limit).all()

    return {
        "meetings": [
            {
                "id": r.id,
                "room_code": r.room_code,
                "room_name": r.room_name,
                "room_description": r.room_description,
                "provider": r.provider,
                "scheduled_start": r.scheduled_start.isoformat() if r.scheduled_start else None,
                "scheduled_end": r.scheduled_end.isoformat() if r.scheduled_end else None,
                "duration_minutes": r.duration_minutes,
                "status": r.status,
                "meeting_type": r.meeting_type,
                "loan_id": r.loan_id,
                "lead_id": r.lead_id,
                "host_user_id": r.host_user_id,
                "recording_enabled": r.recording_enabled,
                "ai_assistant_enabled": r.ai_assistant_enabled,
                "ai_summary": r.ai_summary,
                "ai_action_items": r.ai_action_items,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in rooms
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/rooms")
async def create_meeting_room(
    data: MeetingRoomCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new meeting room."""
    _models = get_models()
    _pwd_context = get_pwd_context()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    MeetingTemplate = _models.get('MeetingTemplate')

    # Block unsupported providers
    unsupported_providers = ("google_meet", "webex")
    if data.provider in unsupported_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{data.provider}' is not yet supported. Supported providers: internal, zoom, teams"
        )

    # Enforce organization-level video settings if available
    OrganizationVideoSettings = _models.get('OrganizationVideoSettings')
    org_id = getattr(current_user, 'organization_id', None)
    org_settings = None
    if OrganizationVideoSettings and org_id:
        try:
            org_settings = db.query(OrganizationVideoSettings).filter(
                OrganizationVideoSettings.organization_id == org_id
            ).first()
        except Exception as e:
            logger.exception(f"Failed to query organization video settings: {e}")

    if org_settings:
        if not org_settings.recording_allowed:
            data.recording_enabled = False
        if org_settings.allowed_providers and data.provider not in org_settings.allowed_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{data.provider}' is not allowed by your organization. Allowed: {org_settings.allowed_providers}"
            )
        if org_settings.max_participants and data.max_participants > org_settings.max_participants:
            data.max_participants = org_settings.max_participants

    # Calculate end time if not provided
    scheduled_end = data.scheduled_end
    if data.scheduled_start and not scheduled_end:
        scheduled_end = data.scheduled_start + timedelta(minutes=data.duration_minutes)

    # Apply template settings if template_id provided
    template_settings = {}
    if data.template_id and MeetingTemplate:
        template = db.query(MeetingTemplate).filter(MeetingTemplate.id == data.template_id).first()
        if template:
            template_settings = {
                'recording_enabled': template.recording_enabled,
                'transcription_enabled': template.transcription_enabled,
                'ai_assistant_enabled': template.ai_assistant_enabled,
                'waiting_room_enabled': template.waiting_room_enabled,
                'duration_minutes': template.default_duration_minutes
            }

    # Generate unique room code with retry on DB-level collision (IntegrityError)
    max_attempts = 3
    for attempt in range(max_attempts):
        room_code = generate_room_code()
        room = VideoMeetingRoom(
            room_code=room_code,
            room_name=data.room_name,
            room_description=data.room_description,
            provider=data.provider,
            host_user_id=current_user.id,
            organization_id=getattr(current_user, 'organization_id', None),
            scheduled_start=data.scheduled_start,
            scheduled_end=scheduled_end,
            duration_minutes=template_settings.get('duration_minutes', data.duration_minutes),
            status="scheduled" if data.scheduled_start else "active",
            waiting_room_enabled=template_settings.get('waiting_room_enabled', data.waiting_room_enabled),
            recording_enabled=template_settings.get('recording_enabled', data.recording_enabled),
            transcription_enabled=template_settings.get('transcription_enabled', data.transcription_enabled),
            ai_assistant_enabled=template_settings.get('ai_assistant_enabled', data.ai_assistant_enabled),
            password_protected=data.password_protected,
            room_password=_pwd_context.hash(data.room_password) if data.password_protected and data.room_password and _pwd_context else data.room_password,
            max_participants=data.max_participants,
            loan_id=data.loan_id,
            lead_id=data.lead_id,
            appointment_id=data.appointment_id,
            meeting_type=data.meeting_type,
            created_by=current_user.id
        )
        db.add(room)
        try:
            db.commit()
            db.refresh(room)
            break
        except IntegrityError:
            db.rollback()
            logger.warning(f"Room code collision on attempt {attempt + 1}: {room_code}")
            if attempt == max_attempts - 1:
                raise HTTPException(status_code=500, detail="Failed to generate unique room code")

    # Add host as participant
    if MeetingParticipant:
        host_participant = MeetingParticipant(
            meeting_id=room.id,
            user_id=current_user.id,
            email=current_user.email,
            display_name=current_user.email.split('@')[0],
            role="host",
            status="invited"
        )
        db.add(host_participant)
        db.commit()

    return {
        "success": True,
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "scheduled_start": room.scheduled_start.isoformat() if room.scheduled_start else None,
            "scheduled_end": room.scheduled_end.isoformat() if room.scheduled_end else None,
            "duration_minutes": room.duration_minutes,
            "status": room.status,
            "join_url": f"/meeting/{room.room_code}",
            "host_url": f"/meeting/{room.room_code}?host=true"
        }
    }


@router.get("/rooms/{room_id}")
async def get_meeting_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get details of a specific meeting room."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if not verify_room_access(room, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    participants = []
    if MeetingParticipant:
        participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id
        ).all()

    recordings = []
    if MeetingRecording:
        recordings = db.query(MeetingRecording).filter(
            MeetingRecording.meeting_id == room_id
        ).all()

    return {
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "room_description": room.room_description,
            "provider": room.provider,
            "external_meeting_url": room.external_meeting_url,
            "host_user_id": room.host_user_id,
            "scheduled_start": room.scheduled_start.isoformat() if room.scheduled_start else None,
            "scheduled_end": room.scheduled_end.isoformat() if room.scheduled_end else None,
            "actual_start": room.actual_start.isoformat() if room.actual_start else None,
            "actual_end": room.actual_end.isoformat() if room.actual_end else None,
            "duration_minutes": room.duration_minutes,
            "status": room.status,
            "meeting_type": room.meeting_type,
            "loan_id": room.loan_id,
            "lead_id": room.lead_id,
            "waiting_room_enabled": room.waiting_room_enabled,
            "recording_enabled": room.recording_enabled,
            "transcription_enabled": room.transcription_enabled,
            "ai_assistant_enabled": room.ai_assistant_enabled,
            "password_protected": room.password_protected,
            "max_participants": room.max_participants,
            "ai_summary": room.ai_summary,
            "ai_action_items": room.ai_action_items,
            "ai_key_topics": room.ai_key_topics,
            "join_url": f"/meeting/{room.room_code}",
            "created_at": room.created_at.isoformat() if room.created_at else None
        },
        "participants": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "email": p.email,
                "display_name": p.display_name,
                "role": p.role,
                "status": p.status,
                "joined_at": p.joined_at.isoformat() if p.joined_at else None,
                "speaking_time_seconds": p.speaking_time_seconds,
                "engagement_score": p.engagement_score
            }
            for p in participants
        ],
        "recordings": [
            {
                "id": r.id,
                "recording_uuid": r.recording_uuid,
                "recording_name": r.recording_name,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in recordings
        ]
    }


@router.put("/rooms/{room_id}")
async def update_meeting_room(
    room_id: int,
    data: MeetingRoomUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update a meeting room."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can update this meeting")

    _protected = {'id', 'host_user_id', 'organization_id', 'room_code', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected:
            setattr(room, field, value)

    room.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(room)

    return {"success": True, "meeting": {"id": room.id, "room_code": room.room_code, "status": room.status}}


@router.delete("/rooms/{room_id}")
async def delete_meeting_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Cancel/delete a meeting room."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can delete this meeting")

    room.status = "cancelled"
    room.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Meeting cancelled"}


@router.post("/rooms/{room_id}/start")
async def start_meeting(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Start a meeting room."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start this meeting")

    room.status = "active"
    room.actual_start = datetime.now(timezone.utc)
    room.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "meeting": {"id": room.id, "status": room.status, "actual_start": room.actual_start.isoformat()}}


@router.post("/rooms/{room_id}/end")
async def end_meeting(
    room_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """End a meeting room."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can end this meeting")

    room.status = "ended"
    room.actual_end = datetime.now(timezone.utc)
    room.updated_at = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(process_meeting_ai_analysis, room_id)

    return {"success": True, "meeting": {"id": room.id, "status": room.status, "actual_end": room.actual_end.isoformat()}}


@router.post("/rooms/{room_id}/invite")
async def send_meeting_invite(
    room_id: int,
    data: MeetingInviteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Send a meeting invite email to a participant."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.status not in ["active", "scheduled"]:
        raise HTTPException(status_code=400, detail="Cannot invite to a cancelled or ended meeting")

    participant_name = data.name or data.email.split('@')[0]
    host_name = data.host_name or current_user.email.split('@')[0]
    meeting_name = data.meeting_name or room.room_name

    existing_participant = None
    if MeetingParticipant:
        existing_participant = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id,
            MeetingParticipant.email == data.email
        ).first()

    if not existing_participant and MeetingParticipant:
        participant = MeetingParticipant(
            meeting_id=room_id,
            email=data.email,
            display_name=participant_name,
            role="participant",
            status="invited"
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)

    try:
        from email_service import send_meeting_invite_email as send_email_invite

        email_sent = await send_email_invite(
            to_email=data.email,
            participant_name=participant_name,
            host_name=host_name,
            meeting_name=meeting_name,
            join_url=data.join_url,
            scheduled_time=room.scheduled_start
        )

        if not email_sent:
            logger.warning(f"Failed to send meeting invite email to {data.email}")
            return {
                "success": True,
                "participant_added": True,
                "email_sent": False,
                "message": "Participant added but email could not be sent"
            }

    except ImportError:
        logger.warning("Email service not available, skipping email send")
        return {
            "success": True,
            "participant_added": True,
            "email_sent": False,
            "message": "Participant added but email service not available"
        }
    except Exception as e:
        logger.error(f"Error sending meeting invite: {e}")
        return {
            "success": True,
            "participant_added": True,
            "email_sent": False,
            "message": "Participant added but email failed"
        }

    return {
        "success": True,
        "participant_added": True,
        "email_sent": True,
        "message": f"Invite sent to {data.email}"
    }


# ============================================================================
# WAITING ROOM ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/waiting-room/join")
async def request_to_join_meeting(
    room_id: int,
    data: WaitingRoomRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Guest requests to join a meeting - adds them to waiting room."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"waiting_room:{client_ip}"):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again in a minute.")

    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.status not in ["active", "scheduled"]:
        raise HTTPException(status_code=400, detail="This meeting is not available to join")

    existing = None
    if MeetingParticipant and data.email:
        existing = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id,
            MeetingParticipant.email == data.email
        ).first()

    if existing:
        existing.status = "waiting"
        existing.display_name = data.display_name
        db.commit()
        participant_id = existing.id
    elif MeetingParticipant:
        participant = MeetingParticipant(
            meeting_id=room_id,
            email=data.email,
            display_name=data.display_name,
            role="participant",
            status="waiting"
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
        participant_id = participant.id
    else:
        participant_id = None

    logger.info(f"Guest {data.display_name} requested to join meeting {room_id}")

    return {
        "success": True,
        "participant_id": participant_id,
        "status": "waiting",
        "message": "Please wait for the host to admit you"
    }


@router.get("/rooms/{room_id}/waiting-room/status/{participant_id}")
async def check_admission_status(
    room_id: int,
    participant_id: int,
    db: Session = Depends(get_db)
):
    """Guest polls to check if they've been admitted."""
    _models = get_models()
    MeetingParticipant = _models.get('MeetingParticipant')

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    return {
        "status": participant.status,
        "admitted": participant.status == "joined",
        "rejected": participant.status == "removed"
    }


@router.get("/rooms/{room_id}/waiting-room")
async def get_waiting_participants(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Host gets list of participants waiting to be admitted."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can view the waiting room")

    waiting_participants = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        MeetingParticipant.status == "waiting"
    ).all()

    return {
        "waiting_count": len(waiting_participants),
        "participants": [
            {
                "id": p.id,
                "display_name": p.display_name,
                "email": p.email,
                "requested_at": p.joined_at.isoformat() if p.joined_at else None
            }
            for p in waiting_participants
        ]
    }


@router.post("/rooms/{room_id}/waiting-room/{participant_id}")
async def admit_or_reject_participant(
    room_id: int,
    participant_id: int,
    data: AdmitParticipantRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Host admits or rejects a waiting participant."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can admit participants")

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    if data.action == "admit":
        participant.status = "joined"
        participant.joined_at = datetime.now(timezone.utc)
        message = f"Admitted {participant.display_name}"
    elif data.action == "reject":
        participant.status = "removed"
        message = f"Rejected {participant.display_name}"
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'admit' or 'reject'")

    db.commit()

    logger.info(f"Host {current_user.id} {data.action}ed participant {participant_id} in meeting {room_id}")

    return {
        "success": True,
        "action": data.action,
        "participant_id": participant_id,
        "message": message
    }


@router.post("/rooms/{room_id}/waiting-room/admit-all")
async def admit_all_waiting(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Host admits all waiting participants at once."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can admit participants")

    waiting = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        MeetingParticipant.status == "waiting"
    ).all()

    admitted_count = 0
    for p in waiting:
        p.status = "joined"
        p.joined_at = datetime.now(timezone.utc)
        admitted_count += 1

    db.commit()

    return {
        "success": True,
        "admitted_count": admitted_count,
        "message": f"Admitted {admitted_count} participant(s)"
    }


# ============================================================================
# PARTICIPANT ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/participants")
async def add_participant(
    room_id: int,
    data: ParticipantAdd,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Add a participant to a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    User = _models.get('User')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    existing = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        or_(
            MeetingParticipant.user_id == data.user_id,
            MeetingParticipant.email == data.email
        )
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Participant already added to this meeting")

    participant = MeetingParticipant(
        meeting_id=room_id,
        user_id=data.user_id,
        email=data.email,
        display_name=data.display_name or data.email.split('@')[0] if data.email else "Guest",
        role=data.role,
        status="invited"
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)

    if data.send_invite and data.email:
        host = db.query(User).filter(User.id == room.host_user_id).first() if User else None
        host_name = host.full_name if host and hasattr(host, 'full_name') else current_user.full_name if hasattr(current_user, 'full_name') else "Host"

        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        join_url = f"{frontend_url}/meeting/{room.room_code}"

        background_tasks.add_task(
            send_meeting_invite_email,
            to_email=data.email,
            participant_name=participant.display_name,
            room_name=room.room_name,
            join_url=join_url,
            host_name=host_name,
            scheduled_start=room.scheduled_start
        )

    return {
        "success": True,
        "participant": {
            "id": participant.id,
            "email": participant.email,
            "display_name": participant.display_name,
            "role": participant.role,
            "status": participant.status
        },
        "invite_sent": data.send_invite and data.email is not None
    }


@router.put("/rooms/{room_id}/participants/{participant_id}")
async def update_participant(
    room_id: int,
    participant_id: int,
    data: ParticipantUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update a participant's settings."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")
    if not verify_host_permission(room, current_user):
        raise HTTPException(status_code=403, detail="Only the host can modify participants")

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    _protected = {'id', 'meeting_id', 'user_id', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected:
            setattr(participant, field, value)

    participant.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "participant": {"id": participant.id, "role": participant.role, "status": participant.status}}


@router.delete("/rooms/{room_id}/participants/{participant_id}")
async def remove_participant(
    room_id: int,
    participant_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Remove a participant from a meeting."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")
    if not verify_host_permission(room, current_user):
        raise HTTPException(status_code=403, detail="Only the host can remove participants")

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.status = "removed"
    participant.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Participant removed"}


# ============================================================================
# INSTANT MEETING
# ============================================================================

@router.post("/instant")
async def create_instant_meeting(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create an instant meeting (start now)."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    max_attempts = 3
    for attempt in range(max_attempts):
        room_code = generate_room_code()
        room = VideoMeetingRoom(
            room_code=room_code,
            room_name=f"Instant Meeting - {datetime.now(timezone.utc).strftime('%b %d, %H:%M')}",
            provider="internal",
            host_user_id=current_user.id,
            organization_id=getattr(current_user, 'organization_id', None),
            scheduled_start=datetime.now(timezone.utc),
            scheduled_end=datetime.now(timezone.utc) + timedelta(minutes=60),
            actual_start=datetime.now(timezone.utc),
            duration_minutes=60,
            status="active",
            waiting_room_enabled=False,
            recording_enabled=True,
            transcription_enabled=True,
            ai_assistant_enabled=True,
            meeting_type="instant",
            created_by=current_user.id
        )
        db.add(room)
        try:
            db.commit()
            db.refresh(room)
            break
        except IntegrityError:
            db.rollback()
            logger.warning(f"Room code collision on instant meeting attempt {attempt + 1}: {room_code}")
            if attempt == max_attempts - 1:
                raise HTTPException(status_code=500, detail="Failed to generate unique room code")

    return {
        "success": True,
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "status": room.status,
            "join_url": f"/meeting/{room.room_code}",
            "host_url": f"/meeting/{room.room_code}?host=true"
        }
    }


# ============================================================================
# JOIN MEETING BY CODE
# ============================================================================

@router.get("/join/{room_code}")
async def join_meeting_by_code(
    room_code: str,
    password: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get meeting room info for joining by room code (public endpoint)."""
    _models = get_models()
    _pwd_context = get_pwd_context()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if room.status == "cancelled":
        raise HTTPException(status_code=400, detail="This meeting has been cancelled")

    if room.status == "ended":
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    if room.password_protected and room.room_password:
        if not password:
            raise HTTPException(status_code=403, detail="This meeting requires a password")
        if _pwd_context:
            if not _pwd_context.verify(password, room.room_password):
                raise HTTPException(status_code=403, detail="Incorrect meeting password")
        else:
            if password != room.room_password:
                raise HTTPException(status_code=403, detail="Incorrect meeting password")

    response = {
        "meeting": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "status": room.status,
            "waiting_room_enabled": room.waiting_room_enabled,
            "password_protected": room.password_protected,
            "scheduled_start": room.scheduled_start.isoformat() if room.scheduled_start else None,
            "meeting_type": room.meeting_type,
            "host_user_id": room.host_user_id,
            "recording_enabled": room.recording_enabled
        }
    }

    # If this is a Chime-backed meeting, include SDK join info
    chime_meeting_id = getattr(room, 'chime_meeting_id', None)
    if chime_meeting_id:
        try:
            from services.chime_meeting_service import get_chime_service
            chime = get_chime_service()
            # Create an attendee — use "guest" as external ID for unauthenticated joins
            attendee = chime.create_attendee(chime_meeting_id, f"guest-{room_code}")
            join_info = chime.get_meeting_join_info(chime_meeting_id, attendee["AttendeeId"])
            response["chime"] = {
                "meeting": join_info["Meeting"],
                "attendee": join_info["Attendee"],
            }
        except Exception as e:
            logger.warning(f"Could not get Chime join info for room {room_code}: {e}")

    return response


# ============================================================================
# DASHBOARD STATS
# ============================================================================

@router.get("/stats")
async def get_meeting_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get meeting statistics for the current user."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    total_meetings = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id
    ).scalar()

    week_start = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
    meetings_this_week = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        VideoMeetingRoom.scheduled_start >= week_start
    ).scalar()

    upcoming = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        VideoMeetingRoom.status.in_(["scheduled", "active"]),
        VideoMeetingRoom.scheduled_start >= datetime.now(timezone.utc)
    ).scalar()

    total_duration = db.query(func.sum(VideoMeetingRoom.duration_minutes)).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        VideoMeetingRoom.status.in_(["ended", "completed"])
    ).scalar() or 0

    return {
        "stats": {
            "total_meetings": total_meetings or 0,
            "meetings_this_week": meetings_this_week or 0,
            "upcoming_meetings": upcoming or 0,
            "total_meeting_hours": round(total_duration / 60, 1)
        }
    }


# ============================================================================
# CRM INTEGRATION ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/link-crm")
async def link_meeting_to_crm(
    room_id: int,
    entity_type: str = Body(...),
    entity_id: int = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Link meeting to a CRM entity (loan, lead, or contact)."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if entity_type == "loan":
        room.loan_id = entity_id
    elif entity_type == "lead":
        room.lead_id = entity_id
    elif entity_type == "contact":
        room.contact_id = entity_id
    else:
        raise HTTPException(status_code=400, detail="Invalid entity type. Use: loan, lead, or contact")

    if not room.settings:
        room.settings = {}
    room.settings["crm_entity_type"] = entity_type
    room.settings["crm_entity_id"] = entity_id

    room.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "linked_to": f"{entity_type}:{entity_id}"
    }


@router.get("/crm/{entity_type}/{entity_id}/meetings")
async def get_entity_meetings(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get all meetings linked to a CRM entity."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    if entity_type == "loan":
        meetings = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.loan_id == entity_id
        ).order_by(VideoMeetingRoom.scheduled_start.desc()).all()
    elif entity_type == "lead":
        meetings = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.lead_id == entity_id
        ).order_by(VideoMeetingRoom.scheduled_start.desc()).all()
    elif entity_type == "contact":
        meetings = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.contact_id == entity_id
        ).order_by(VideoMeetingRoom.scheduled_start.desc()).all()
    else:
        raise HTTPException(status_code=400, detail="Invalid entity type")

    return {
        "meetings": [
            {
                "id": m.id,
                "room_code": m.room_code,
                "room_name": m.room_name,
                "meeting_type": m.meeting_type,
                "scheduled_start": m.scheduled_start.isoformat() if m.scheduled_start else None,
                "status": m.status,
                "duration_minutes": m.duration_minutes,
                "has_recording": False,
                "ai_summary": m.ai_summary[:200] + "..." if m.ai_summary and len(m.ai_summary) > 200 else m.ai_summary
            }
            for m in meetings
        ],
        "total": len(meetings)
    }


