"""
UVIP - Ultimate Video Intelligence Platform API Routes
Phase 1: Core Meeting Infrastructure

API endpoints for:
- Meeting room CRUD operations
- Participant management
- Recording management
- Meeting templates
- AI analysis requests
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path, BackgroundTasks, Body
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import logging
import secrets
import string

from video_meeting_models import (
    MeetingRoomStatus, ParticipantRole, ParticipantStatus,
    RecordingStatus, TranscriptStatus, MeetingProvider,
    AIAnalysisType, DEFAULT_MEETING_TEMPLATES
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meetings", tags=["Video Meetings"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


def generate_room_code(length: int = 9) -> str:
    """Generate a unique meeting room code like MTG-ABC123"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(chars) for _ in range(length))
    return f"MTG-{code[:3]}-{code[3:6]}-{code[6:]}"


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class MeetingRoomCreate(BaseModel):
    room_name: str
    room_description: Optional[str] = None
    provider: str = "internal"
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    duration_minutes: int = 30
    waiting_room_enabled: bool = True
    recording_enabled: bool = True
    transcription_enabled: bool = True
    ai_assistant_enabled: bool = True
    password_protected: bool = False
    room_password: Optional[str] = None
    max_participants: int = 50
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    appointment_id: Optional[int] = None
    meeting_type: str = "general"
    template_id: Optional[int] = None


class MeetingRoomUpdate(BaseModel):
    room_name: Optional[str] = None
    room_description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    waiting_room_enabled: Optional[bool] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    ai_assistant_enabled: Optional[bool] = None
    password_protected: Optional[bool] = None
    room_password: Optional[str] = None
    max_participants: Optional[int] = None
    status: Optional[str] = None


class ParticipantAdd(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "participant"
    send_invite: bool = True


class ParticipantUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    can_share_screen: Optional[bool] = None
    can_unmute: Optional[bool] = None
    can_chat: Optional[bool] = None


class MeetingTemplateCreate(BaseModel):
    template_name: str
    template_key: str
    description: Optional[str] = None
    default_duration_minutes: int = 30
    waiting_room_enabled: bool = True
    recording_enabled: bool = True
    transcription_enabled: bool = True
    ai_assistant_enabled: bool = True
    default_agenda: Optional[List[Dict]] = None
    color: str = "#3b82f6"
    icon: str = "video"


class MeetingTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    description: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    waiting_room_enabled: Optional[bool] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    ai_assistant_enabled: Optional[bool] = None
    default_agenda: Optional[List[Dict]] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


class AvailableSlotsRequest(BaseModel):
    start_date: date
    end_date: date
    duration_minutes: int = 30


class AIAnalysisRequest(BaseModel):
    analysis_types: List[str] = ["summary", "action_items"]
    custom_prompt: Optional[str] = None


# ============================================================================
# MEETING ROOM ENDPOINTS
# ============================================================================

@router.get("/rooms")
async def list_meeting_rooms(
    status: Optional[str] = None,
    meeting_type: Optional[str] = None,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all meeting rooms for the current user."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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
    current_user = Depends(get_current_user)
):
    """Create a new meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    MeetingTemplate = _models.get('MeetingTemplate')

    # Generate unique room code
    room_code = generate_room_code()
    while db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first():
        room_code = generate_room_code()

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
        room_password=data.room_password,
        max_participants=data.max_participants,
        loan_id=data.loan_id,
        lead_id=data.lead_id,
        appointment_id=data.appointment_id,
        meeting_type=data.meeting_type,
        created_by=current_user.id
    )

    db.add(room)
    db.commit()
    db.refresh(room)

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
    current_user = Depends(get_current_user)
):
    """Get details of a specific meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Get participants
    participants = []
    if MeetingParticipant:
        participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id
        ).all()

    # Get recordings
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
    current_user = Depends(get_current_user)
):
    """Update a meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Check permission
    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can update this meeting")

    # Update fields
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(room, field, value)

    room.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(room)

    return {"success": True, "meeting": {"id": room.id, "room_code": room.room_code, "status": room.status}}


@router.delete("/rooms/{room_id}")
async def delete_meeting_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Cancel/delete a meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can delete this meeting")

    # Mark as cancelled instead of hard delete
    room.status = "cancelled"
    room.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Meeting cancelled"}


@router.post("/rooms/{room_id}/start")
async def start_meeting(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start a meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    room.status = "active"
    room.actual_start = datetime.utcnow()
    room.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "meeting": {"id": room.id, "status": room.status, "actual_start": room.actual_start.isoformat()}}


@router.post("/rooms/{room_id}/end")
async def end_meeting(
    room_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """End a meeting room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    room.status = "ended"
    room.actual_end = datetime.utcnow()
    room.updated_at = datetime.utcnow()
    db.commit()

    # TODO: Trigger AI analysis in background
    # background_tasks.add_task(process_meeting_ai_analysis, room_id)

    return {"success": True, "meeting": {"id": room.id, "status": room.status, "actual_end": room.actual_end.isoformat()}}


# ============================================================================
# PARTICIPANT ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/participants")
async def add_participant(
    room_id: int,
    data: ParticipantAdd,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a participant to a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Check if participant already exists
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

    # TODO: Send invite email if send_invite is True

    return {
        "success": True,
        "participant": {
            "id": participant.id,
            "email": participant.email,
            "display_name": participant.display_name,
            "role": participant.role,
            "status": participant.status
        }
    }


@router.put("/rooms/{room_id}/participants/{participant_id}")
async def update_participant(
    room_id: int,
    participant_id: int,
    data: ParticipantUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a participant's settings."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingParticipant = _models.get('MeetingParticipant')

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(participant, field, value)

    participant.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "participant": {"id": participant.id, "role": participant.role, "status": participant.status}}


@router.delete("/rooms/{room_id}/participants/{participant_id}")
async def remove_participant(
    room_id: int,
    participant_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a participant from a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingParticipant = _models.get('MeetingParticipant')

    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.id == participant_id,
        MeetingParticipant.meeting_id == room_id
    ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.status = "removed"
    participant.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Participant removed"}


# ============================================================================
# TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all meeting templates."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        return {"templates": DEFAULT_MEETING_TEMPLATES}

    templates = db.query(MeetingTemplate).filter(
        or_(
            MeetingTemplate.is_system_template == True,
            MeetingTemplate.organization_id == getattr(current_user, 'organization_id', None)
        ),
        MeetingTemplate.is_active == True
    ).all()

    return {
        "templates": [
            {
                "id": t.id,
                "template_key": t.template_key,
                "template_name": t.template_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "recording_enabled": t.recording_enabled,
                "ai_assistant_enabled": t.ai_assistant_enabled,
                "default_agenda": t.default_agenda,
                "color": t.color,
                "icon": t.icon,
                "is_system_template": t.is_system_template
            }
            for t in templates
        ]
    }


@router.post("/templates")
async def create_template(
    data: MeetingTemplateCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new meeting template."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = MeetingTemplate(
        template_name=data.template_name,
        template_key=data.template_key,
        description=data.description,
        organization_id=getattr(current_user, 'organization_id', None),
        is_system_template=False,
        default_duration_minutes=data.default_duration_minutes,
        waiting_room_enabled=data.waiting_room_enabled,
        recording_enabled=data.recording_enabled,
        transcription_enabled=data.transcription_enabled,
        ai_assistant_enabled=data.ai_assistant_enabled,
        default_agenda=data.default_agenda or [],
        color=data.color,
        icon=data.icon,
        created_by=current_user.id
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return {"success": True, "template": {"id": template.id, "template_key": template.template_key}}


@router.post("/templates/seed-defaults")
async def seed_default_templates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Seed default meeting templates."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    created = 0
    for template_data in DEFAULT_MEETING_TEMPLATES:
        existing = db.query(MeetingTemplate).filter(
            MeetingTemplate.template_key == template_data['template_key']
        ).first()

        if not existing:
            template = MeetingTemplate(
                template_key=template_data['template_key'],
                template_name=template_data['template_name'],
                description=template_data['description'],
                default_duration_minutes=template_data['default_duration_minutes'],
                recording_enabled=template_data['recording_enabled'],
                ai_assistant_enabled=template_data['ai_assistant_enabled'],
                default_agenda=template_data['default_agenda'],
                color=template_data['color'],
                icon=template_data['icon'],
                is_system_template=True,
                is_active=True
            )
            db.add(template)
            created += 1

    db.commit()

    return {"success": True, "message": f"Seeded {created} default templates"}


# ============================================================================
# RECORDING ENDPOINTS
# ============================================================================

@router.get("/rooms/{room_id}/recordings")
async def list_recordings(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all recordings for a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingRecording = _models.get('MeetingRecording')
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
    current_user = Depends(get_current_user)
):
    """Start recording a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

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
    current_user = Depends(get_current_user)
):
    """Stop recording a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingRecording = _models.get('MeetingRecording')

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

    # TODO: Trigger recording processing in background
    # background_tasks.add_task(process_recording, recording_id)

    return {"success": True, "recording": {"id": recording.id, "status": recording.status, "duration_seconds": recording.duration_seconds}}


# ============================================================================
# AI ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/ai-analysis")
async def request_ai_analysis(
    room_id: int,
    data: AIAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Request AI analysis for a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingAIAnalysis = _models.get('MeetingAIAnalysis')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.status not in ["ended", "completed"]:
        raise HTTPException(status_code=400, detail="Meeting must be ended before AI analysis")

    analyses_created = []
    for analysis_type in data.analysis_types:
        analysis = MeetingAIAnalysis(
            meeting_id=room_id,
            analysis_type=analysis_type,
            status="pending",
            created_by=current_user.id
        )
        db.add(analysis)
        analyses_created.append(analysis_type)

    db.commit()

    # TODO: Trigger AI analysis in background
    # background_tasks.add_task(run_ai_analysis, room_id, data.analysis_types)

    return {"success": True, "analyses_requested": analyses_created}


@router.get("/rooms/{room_id}/ai-analysis")
async def get_ai_analysis(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get AI analysis results for a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingAIAnalysis = _models.get('MeetingAIAnalysis')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Get analysis results from MeetingAIAnalysis table
    analyses = []
    if MeetingAIAnalysis:
        analyses = db.query(MeetingAIAnalysis).filter(
            MeetingAIAnalysis.meeting_id == room_id
        ).all()

    return {
        "meeting_id": room_id,
        "summary": room.ai_summary,
        "action_items": room.ai_action_items,
        "key_topics": room.ai_key_topics,
        "follow_up_recommended": room.ai_follow_up_recommended,
        "analyses": [
            {
                "id": a.id,
                "analysis_type": a.analysis_type,
                "status": a.status,
                "content": a.content,
                "structured_content": a.structured_content,
                "confidence_score": a.confidence_score,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in analyses
        ]
    }


# ============================================================================
# INSTANT MEETING
# ============================================================================

@router.post("/instant")
async def create_instant_meeting(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create an instant meeting (start now)."""
    data = MeetingRoomCreate(
        room_name=f"Instant Meeting - {datetime.utcnow().strftime('%b %d, %H:%M')}",
        scheduled_start=datetime.utcnow(),
        duration_minutes=60
    )

    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room_code = generate_room_code()
    while db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first():
        room_code = generate_room_code()

    room = VideoMeetingRoom(
        room_code=room_code,
        room_name=data.room_name,
        provider="internal",
        host_user_id=current_user.id,
        organization_id=getattr(current_user, 'organization_id', None),
        scheduled_start=datetime.utcnow(),
        scheduled_end=datetime.utcnow() + timedelta(minutes=60),
        actual_start=datetime.utcnow(),
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
    db.commit()
    db.refresh(room)

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
    db: Session = Depends(get_db)
):
    """Get meeting room info for joining by room code (public endpoint)."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if room.status == "cancelled":
        raise HTTPException(status_code=400, detail="This meeting has been cancelled")

    if room.status == "ended":
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    return {
        "meeting": {
            "room_code": room.room_code,
            "room_name": room.room_name,
            "status": room.status,
            "waiting_room_enabled": room.waiting_room_enabled,
            "password_protected": room.password_protected,
            "scheduled_start": room.scheduled_start.isoformat() if room.scheduled_start else None,
            "meeting_type": room.meeting_type
        }
    }


# ============================================================================
# DASHBOARD STATS
# ============================================================================

@router.get("/stats")
async def get_meeting_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get meeting statistics for the current user."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    # Total meetings
    total_meetings = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id
    ).scalar()

    # Meetings this week
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    meetings_this_week = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        VideoMeetingRoom.scheduled_start >= week_start
    ).scalar()

    # Upcoming meetings
    upcoming = db.query(func.count(VideoMeetingRoom.id)).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        VideoMeetingRoom.status.in_(["scheduled", "active"]),
        VideoMeetingRoom.scheduled_start >= datetime.utcnow()
    ).scalar()

    # Total meeting hours (completed meetings)
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

    try:
        from uvip.recording_service import get_recording_service
        recording_service = get_recording_service()

        # Get caller info from Twilio request
        form_data = await request.form()
        caller = form_data.get("Caller", "Unknown")
        caller_name = form_data.get("CallerName", caller)

        # Generate conference TwiML
        twiml = recording_service.get_conference_twiml(
            meeting_room_id=room_code,
            participant_name=caller_name,
            is_host=False  # First caller or determined by other logic
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
    if _models is None:
        return {"error": "Models not initialized"}

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

        # Find the meeting room
        room = db.query(VideoMeetingRoom).filter(
            VideoMeetingRoom.room_code == room_code
        ).first()

        if not room:
            logger.error(f"Meeting room {room_code} not found for recording callback")
            return {"error": "Meeting not found"}

        # Create recording record
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

        # Trigger AI processing in background
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
        return {"error": str(e)}


@router.post("/twilio/call-status/{room_code}")
async def twilio_call_status_callback(
    room_code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Twilio call status updates."""
    try:
        form_data = await request.form()

        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")

        logger.info(f"Call status update for {room_code}: SID={call_sid}, Status={call_status}")

        # Update participant status based on call status
        if _models:
            MeetingParticipant = _models.get('MeetingParticipant')
            VideoMeetingRoom = _models.get('VideoMeetingRoom')

            room = db.query(VideoMeetingRoom).filter(
                VideoMeetingRoom.room_code == room_code
            ).first()

            if room and MeetingParticipant:
                # Find participant by call SID (stored in settings)
                # Update their status accordingly
                pass

        return {"status": "acknowledged"}

    except Exception as e:
        logger.error(f"Call status callback error: {e}")
        return {"error": str(e)}


async def process_recording_ai(recording_id: int, meeting_id: int, transcription_enabled: bool):
    """Background task to process recording with AI."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.recording_service import get_recording_service
        from uvip.ai_processing_service import get_ai_processing_service

        recording_service = get_recording_service()
        ai_service = get_ai_processing_service()

        MeetingRecording = _models.get('MeetingRecording')
        RecordingTranscript = _models.get('RecordingTranscript')
        MeetingAIAnalysis = _models.get('MeetingAIAnalysis')
        VideoMeetingRoom = _models.get('VideoMeetingRoom')

        recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
        if not recording:
            return

        room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == meeting_id).first()
        if not room:
            return

        # Step 1: Download recording from Twilio
        audio_content = await recording_service.download_recording(recording.recording_uuid)
        if not audio_content:
            recording.status = "failed"
            recording.error_message = "Failed to download recording"
            db.commit()
            return

        recording.file_size_bytes = len(audio_content)

        # Step 2: Transcribe if enabled
        transcript_text = ""
        if transcription_enabled and RecordingTranscript:
            transcription_result = await ai_service.transcribe_audio(audio_content)

            if transcription_result.get("transcript"):
                transcript = RecordingTranscript(
                    recording_id=recording.id,
                    meeting_id=meeting_id,
                    status="completed",
                    full_transcript=transcription_result["transcript"],
                    transcript_json=transcription_result.get("segments", []),
                    transcription_provider="whisper",
                    language=transcription_result.get("language", "en"),
                    word_count=len(transcription_result["transcript"].split()),
                    processing_completed_at=datetime.utcnow()
                )
                db.add(transcript)
                db.commit()

                transcript_text = transcription_result["transcript"]

        # Step 3: AI Analysis
        if transcript_text and MeetingAIAnalysis:
            meeting_context = {
                "title": room.room_name,
                "meeting_type": room.meeting_type,
                "participants": [],
                "duration_minutes": recording.duration_seconds // 60 if recording.duration_seconds else 0
            }

            analysis_result = await ai_service.analyze_meeting(transcript_text, meeting_context)

            if not analysis_result.get("error"):
                # Save structured analysis
                analysis = MeetingAIAnalysis(
                    meeting_id=meeting_id,
                    recording_id=recording.id,
                    analysis_type="full_analysis",
                    status="completed",
                    content=analysis_result.get("summary"),
                    structured_content=analysis_result,
                    model_provider="anthropic",
                    model_name="claude-sonnet-4"
                )
                db.add(analysis)

                # Update room with AI summary
                room.ai_summary = analysis_result.get("summary")
                room.ai_action_items = analysis_result.get("action_items")
                room.ai_key_topics = analysis_result.get("key_topics")

        # Mark recording as ready
        recording.status = "ready"
        recording.processing_completed_at = datetime.utcnow()
        db.commit()

        logger.info(f"Recording {recording_id} processed successfully")

    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        if db:
            recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
            if recording:
                recording.status = "failed"
                recording.error_message = str(e)
                db.commit()
    finally:
        db.close()


# ============================================================================
# CRM INTEGRATION ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/link-crm")
async def link_meeting_to_crm(
    room_id: int,
    entity_type: str = Body(...),  # loan, lead, contact
    entity_id: int = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Link meeting to a CRM entity (loan, lead, or contact)."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Update the appropriate foreign key
    if entity_type == "loan":
        room.loan_id = entity_id
    elif entity_type == "lead":
        room.lead_id = entity_id
    elif entity_type == "contact":
        room.contact_id = entity_id
    else:
        raise HTTPException(status_code=400, detail="Invalid entity type. Use: loan, lead, or contact")

    # Store additional metadata
    if not room.settings:
        room.settings = {}
    room.settings["crm_entity_type"] = entity_type
    room.settings["crm_entity_id"] = entity_id

    room.updated_at = datetime.utcnow()
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
    current_user = Depends(get_current_user)
):
    """Get all meetings linked to a CRM entity."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    # Build query based on entity type
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
                "has_recording": False,  # Would need to check recordings table
                "ai_summary": m.ai_summary[:200] + "..." if m.ai_summary and len(m.ai_summary) > 200 else m.ai_summary
            }
            for m in meetings
        ],
        "total": len(meetings)
    }


# ============================================================================
# RECORDING TRANSCRIPT & ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/transcript")
async def get_recording_transcript(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get transcript for a recording."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

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
    current_user = Depends(get_current_user)
):
    """Get AI analysis for a recording."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

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
    current_user = Depends(get_current_user)
):
    """Reprocess a recording for AI analysis."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    MeetingRecording = _models.get('MeetingRecording')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Reset status and trigger reprocessing
    recording.status = "processing"
    db.commit()

    background_tasks.add_task(
        process_recording_ai,
        recording.id,
        recording.meeting_id,
        True  # Enable transcription
    )

    return {"success": True, "status": "reprocessing"}


# ============================================================================
# PHONE DIAL-OUT FOR MEETINGS
# ============================================================================

@router.post("/rooms/{room_code}/dial-participant")
async def dial_participant(
    room_code: str,
    phone_number: str = Body(...),
    participant_name: str = Body(default="Participant"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Dial out to a participant and connect them to the meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if room.status not in ["scheduled", "active", "waiting"]:
        raise HTTPException(status_code=400, detail="Meeting is not active")

    try:
        from uvip.recording_service import get_recording_service
        recording_service = get_recording_service()

        if not recording_service.enabled:
            raise HTTPException(status_code=503, detail="Telephony service not available")

        # Get user's caller ID
        from_phone = recording_service.from_number

        # Start the call
        call_sid = await recording_service.start_recorded_call(
            meeting_room_id=room_code,
            participant_phone=phone_number,
            from_phone=from_phone,
            participant_name=participant_name
        )

        if not call_sid:
            raise HTTPException(status_code=500, detail="Failed to initiate call")

        # Create participant record
        if MeetingParticipant:
            participant = MeetingParticipant(
                meeting_id=room.id,
                display_name=participant_name,
                role="participant",
                status="invited",
                device_type="phone"
            )
            # Store call SID for tracking
            participant.connection_quality = call_sid  # Temporary storage

            db.add(participant)
            db.commit()

        return {
            "success": True,
            "call_sid": call_sid,
            "phone_number": phone_number,
            "participant_name": participant_name
        }

    except Exception as e:
        logger.error(f"Dial participant error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
