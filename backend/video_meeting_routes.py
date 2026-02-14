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
from pydantic import BaseModel, EmailStr, validator
import logging
import os
from pathlib import Path
import secrets
import string
import time
from collections import defaultdict

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
_pwd_context = None


def set_dependencies(get_db_func, get_current_user_func, models_dict, pwd_context=None):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models, _pwd_context
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict
    _pwd_context = pwd_context


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


def _require_admin(current_user):
    """Raise 403 if user is not an admin or site_admin."""
    role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
    if role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")


async def _validate_twilio_signature(request: Request) -> bool:
    """Validate Twilio request signature. Returns True if valid or if validation is not configured."""
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping Twilio signature validation")
        return True

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)

        signature = request.headers.get("X-Twilio-Signature", "")
        form_data = await request.form()
        params = {k: v for k, v in form_data.items()}

        # Reconstruct the full URL Twilio used
        url = str(request.url)

        return validator.validate(url, params, signature)
    except ImportError:
        logger.warning("twilio package not installed — skipping signature validation")
        return True
    except Exception as e:
        logger.error(f"Twilio signature validation error: {e}")
        return False


# In-memory rate limiter for unauthenticated endpoints
_rate_limit_store: Dict[str, list] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10  # max requests per window per IP
_RATE_LIMIT_MAX_KEYS = 10000  # max tracked IPs before forced cleanup


def _check_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limit. Returns True if allowed."""
    now = time.time()
    # Prune old entries for this IP
    _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]
    # Periodic global cleanup to prevent unbounded growth
    if len(_rate_limit_store) > _RATE_LIMIT_MAX_KEYS:
        stale_keys = [k for k, v in _rate_limit_store.items() if not v or now - v[-1] > _RATE_LIMIT_WINDOW]
        for k in stale_keys:
            del _rate_limit_store[k]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[client_ip].append(now)
    return True


# ============================================================================
# AUTHORIZATION HELPERS
# ============================================================================

def verify_room_access(room, current_user, db) -> bool:
    """
    Verify user has access to a meeting room.
    Access is granted if:
    - User is the host
    - User is a participant
    - User is in the same organization (if org tracking enabled)
    """
    if room.host_user_id == current_user.id:
        return True

    # Check if user is a participant
    MeetingParticipant = _models.get('MeetingParticipant')
    participant = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room.id,
        MeetingParticipant.user_id == current_user.id
    ).first()
    if participant:
        return True

    # Check organization access (if organizations are used)
    if hasattr(room, 'organization_id') and hasattr(current_user, 'organization_id'):
        if room.organization_id and room.organization_id == current_user.organization_id:
            return True

    return False


def verify_recording_access(recording_id: int, current_user, db) -> bool:
    """Verify user has access to a recording by checking the parent meeting"""
    MeetingRecording = _models.get('MeetingRecording')
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    recording = db.query(MeetingRecording).filter(
        MeetingRecording.id == recording_id
    ).first()
    if not recording:
        return False

    room = db.query(VideoMeetingRoom).filter(
        VideoMeetingRoom.id == recording.meeting_id
    ).first()
    if not room:
        return False

    return verify_room_access(room, current_user, db)


def verify_host_permission(room, current_user) -> bool:
    """Verify user is the host of a meeting (for admin operations)"""
    return room.host_user_id == current_user.id


# ============================================================================
# BACKGROUND TASK FUNCTIONS
# ============================================================================

async def process_meeting_ai_analysis(room_id: int):
    """Process AI analysis for a completed meeting"""
    from database import SessionLocal
    from services.document_analysis_service import DocumentAnalysisService

    db = SessionLocal()
    try:
        VideoMeetingRoom = _models.get('VideoMeetingRoom')
        MeetingRecording = _models.get('MeetingRecording')
        MeetingTranscript = _models.get('RecordingTranscript')
        AIAnalysis = _models.get('MeetingAIAnalysis')

        room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
        if not room:
            logger.error(f"Meeting room {room_id} not found for AI analysis")
            return

        # Get transcript if available
        transcript = db.query(MeetingTranscript).filter(
            MeetingTranscript.meeting_id == room_id,
            MeetingTranscript.status == "completed"
        ).first()

        if transcript and transcript.full_transcript:
            # Create AI analysis using Claude
            import httpx
            import os

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 2000,
                            "messages": [{
                                "role": "user",
                                "content": f"""Analyze this meeting transcript and provide:
1. Summary (2-3 sentences)
2. Key action items
3. Important decisions made
4. Follow-up items needed

Transcript:
{transcript.full_transcript[:10000]}"""
                            }],
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        analysis_text = result["content"][0]["text"]

                        # Create analysis record
                        analysis = AIAnalysis(
                            meeting_id=room_id,
                            analysis_type="summary",
                            status="completed",
                            result={"summary": analysis_text},
                            completed_at=datetime.utcnow()
                        )
                        db.add(analysis)
                        db.commit()
                        logger.info(f"AI analysis completed for meeting {room_id}")

            except Exception as e:
                logger.error(f"AI analysis failed for meeting {room_id}: {e}")

    except Exception as e:
        logger.error(f"Error processing AI analysis for meeting {room_id}: {e}")
    finally:
        db.close()


async def process_recording(recording_id: int):
    """Process a completed recording (transcription, analysis)"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        MeetingRecording = _models.get('MeetingRecording')
        RecordingTranscript = _models.get('RecordingTranscript')

        recording = db.query(MeetingRecording).filter(
            MeetingRecording.id == recording_id
        ).first()

        if not recording:
            logger.error(f"Recording {recording_id} not found for processing")
            return

        # Update recording status to processing
        recording.status = "processing"
        db.commit()

        # If transcription is enabled, create transcript placeholder
        if recording.storage_path and RecordingTranscript:
            transcript = RecordingTranscript(
                meeting_id=recording.meeting_id,
                recording_id=recording_id,
                status="pending",
                language="en"
            )
            db.add(transcript)
            db.commit()

            # Note: Actual transcription would integrate with Whisper or similar
            logger.info(f"Recording {recording_id} queued for transcription")

        # Don't mark as "completed" yet — leave as "processing" until
        # transcription is actually done. Only mark error on failure.
        logger.info(f"Recording {recording_id} processing started")

    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        # Mark recording with error status for retry visibility
        try:
            recording = db.query(_models.get('MeetingRecording')).filter(
                _models.get('MeetingRecording').id == recording_id
            ).first()
            if recording:
                recording.status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def run_ai_analysis(room_id: int, analysis_types: List[str]):
    """Run specific AI analysis types for a meeting"""
    await process_meeting_ai_analysis(room_id)


async def send_meeting_invite_email(
    to_email: str,
    participant_name: str,
    room_name: str,
    join_url: str,
    host_name: str,
    scheduled_start: Optional[datetime] = None
):
    """Send meeting invite email to participant"""
    from email_service import email_service

    time_str = scheduled_start.strftime('%B %d, %Y at %I:%M %p') if scheduled_start else "Now"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%); color: white; padding: 30px; border-radius: 12px; text-align: center;">
            <h2 style="margin: 0 0 10px;">📹 Video Meeting Invitation</h2>
            <p style="margin: 0; opacity: 0.9;">{room_name}</p>
        </div>

        <div style="padding: 30px 0;">
            <p>Hi {participant_name or 'there'},</p>
            <p>You've been invited to join a video meeting hosted by <strong>{host_name}</strong>.</p>

            <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0 0 5px; color: #666;">When:</p>
                <p style="margin: 0; font-size: 18px; font-weight: 600;">{time_str}</p>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{join_url}"
                   style="display: inline-block; background: #10b981; color: white; padding: 14px 40px;
                          border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                    Join Meeting
                </a>
            </div>

            <p style="color: #666; font-size: 14px; text-align: center;">
                Or copy this link: <a href="{join_url}" style="color: #3b82f6;">{join_url}</a>
            </p>
        </div>

        <div style="border-top: 1px solid #e5e7eb; padding-top: 20px; text-align: center; color: #9ca3af; font-size: 12px;">
            <p>This invitation was sent via Perennia AI CRM</p>
        </div>
    </body>
    </html>
    """

    plain_text = f"""
Video Meeting Invitation

Hi {participant_name or 'there'},

You've been invited to join a video meeting.

Meeting: {room_name}
Host: {host_name}
When: {time_str}

Join the meeting: {join_url}

This invitation was sent via Perennia AI CRM
"""

    success = email_service.send_html_email(
        to_email=to_email,
        subject=f"📹 Video Meeting: {room_name}",
        html_body=html_body,
        plain_text_body=plain_text
    )

    logger.info(f"Meeting invite sent to {to_email}: {'success' if success else 'failed'}")
    return success


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
    status: Optional[MeetingRoomStatus] = None


class ParticipantAdd(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: ParticipantRole = ParticipantRole.PARTICIPANT
    send_invite: bool = True


class ParticipantUpdate(BaseModel):
    role: Optional[ParticipantRole] = None
    status: Optional[ParticipantStatus] = None
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
    analysis_types: List[AIAnalysisType] = [AIAnalysisType.SUMMARY, AIAnalysisType.ACTION_ITEMS]
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
        except Exception:
            pass  # Table may not exist yet

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

    # Generate unique room code (with collision guard)
    room_code = generate_room_code()
    for _ in range(10):
        if not db.query(VideoMeetingRoom).filter(VideoMeetingRoom.room_code == room_code).first():
            break
        room_code = generate_room_code()
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique room code")

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
        room_password=_pwd_context.hash(data.room_password) if data.password_protected and data.room_password and _pwd_context else data.room_password,
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

    # SECURITY: Verify user has access to this room
    if not verify_room_access(room, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

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
    _protected = {'id', 'host_user_id', 'organization_id', 'room_code', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected:
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

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can start this meeting")

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

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can end this meeting")

    room.status = "ended"
    room.actual_end = datetime.utcnow()
    room.updated_at = datetime.utcnow()
    db.commit()

    # Trigger AI analysis in background
    background_tasks.add_task(process_meeting_ai_analysis, room_id)

    return {"success": True, "meeting": {"id": room.id, "status": room.status, "actual_end": room.actual_end.isoformat()}}


class MeetingInviteRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    join_url: str
    meeting_name: Optional[str] = "Video Meeting"
    host_name: Optional[str] = None


@router.post("/rooms/{room_id}/invite")
async def send_meeting_invite(
    room_id: int,
    data: MeetingInviteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send a meeting invite email to a participant."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Allow any authenticated user to send invites for active/scheduled meetings
    # This is less restrictive since invites are helpful and don't expose sensitive data
    if room.status not in ["active", "scheduled"]:
        raise HTTPException(status_code=400, detail="Cannot invite to a cancelled or ended meeting")

    # Get participant name
    participant_name = data.name or data.email.split('@')[0]
    host_name = data.host_name or current_user.email.split('@')[0]
    meeting_name = data.meeting_name or room.room_name

    # Check if participant already exists
    existing_participant = None
    if MeetingParticipant:
        existing_participant = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id,
            MeetingParticipant.email == data.email
        ).first()

    # Add participant if not exists
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

    # Send the email invite
    try:
        from email_service import send_meeting_invite_email

        email_sent = await send_meeting_invite_email(
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

class WaitingRoomRequest(BaseModel):
    display_name: str
    email: Optional[str] = None


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

    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    if room.status not in ["active", "scheduled"]:
        raise HTTPException(status_code=400, detail="This meeting is not available to join")

    # Check if participant already exists
    existing = None
    if MeetingParticipant and data.email:
        existing = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id,
            MeetingParticipant.email == data.email
        ).first()

    if existing:
        # Update status to waiting
        existing.status = "waiting"
        existing.display_name = data.display_name
        db.commit()
        participant_id = existing.id
    elif MeetingParticipant:
        # Create new waiting participant
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
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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
    current_user = Depends(get_current_user)
):
    """Host gets list of participants waiting to be admitted."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Only host can see waiting room
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


class AdmitParticipantRequest(BaseModel):
    action: str  # "admit" or "reject"


@router.post("/rooms/{room_id}/waiting-room/{participant_id}")
async def admit_or_reject_participant(
    room_id: int,
    participant_id: int,
    data: AdmitParticipantRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Host admits or rejects a waiting participant."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Meeting room not found")

    # Only host can admit/reject
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
        participant.joined_at = datetime.utcnow()
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
    current_user = Depends(get_current_user)
):
    """Host admits all waiting participants at once."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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
        p.joined_at = datetime.utcnow()
        admitted_count += 1

    db.commit()

    return {
        "success": True,
        "admitted_count": admitted_count,
        "message": f"Admitted {admitted_count} participant(s)"
    }


# ============================================================================
# SCREEN RECORDING ENDPOINTS
# ============================================================================

from fastapi import File, UploadFile, Form
import uuid
import os

# Storage for screen recordings (in production, use S3 or similar)
SCREEN_RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "screen_recordings")
os.makedirs(SCREEN_RECORDINGS_DIR, exist_ok=True)

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_RECORDING_EXTENSIONS = {"webm", "mp4", "mkv"}
UPLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB


@router.post("/screen-recordings/upload")
async def upload_screen_recording(
    request: Request,
    file: UploadFile = File(...),
    meeting_id: Optional[str] = Form(None),
    room_code: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Upload a screen recording and return a shareable link."""
    try:
        # Validate file extension using pathlib for safe parsing
        file_ext = Path(file.filename).suffix.lower().lstrip('.') if file.filename else ''
        if not file_ext:
            file_ext = 'webm'
        if file_ext not in ALLOWED_RECORDING_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '.{file_ext}'. Allowed: {', '.join(ALLOWED_RECORDING_EXTENSIONS)}"
            )

        # Generate unique filename and resolve path to prevent traversal
        recording_id = str(uuid.uuid4())
        filename = f"{recording_id}.{file_ext}"
        filepath = Path(SCREEN_RECORDINGS_DIR).resolve() / filename
        if not str(filepath).startswith(str(Path(SCREEN_RECORDINGS_DIR).resolve())):
            raise HTTPException(status_code=400, detail="Invalid file path")
        filepath = str(filepath)

        # Stream file to disk in chunks with size enforcement
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
        except Exception:
            # Clean up partial file on write error
            if os.path.exists(filepath):
                os.remove(filepath)
            raise

        if total_size > MAX_UPLOAD_SIZE:
            # Clean up partial file
            if os.path.exists(filepath):
                os.remove(filepath)
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB"
            )

        # Generate shareable URL from request origin or BACKEND_URL env var
        base_url = os.getenv('BACKEND_URL', str(request.base_url).rstrip('/'))
        share_url = f"{base_url}/api/v1/meetings/screen-recordings/{recording_id}"

        # Log recording metadata
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
    current_user = Depends(get_current_user)
):
    """Retrieve a screen recording by ID (authenticated endpoint)."""
    from fastapi.responses import FileResponse

    # Validate recording_id format (UUID-like, alphanumeric + hyphens only)
    import re
    if not re.match(r'^[a-zA-Z0-9\-]+$', recording_id):
        raise HTTPException(status_code=400, detail="Invalid recording ID")

    # Find the recording file with path safety check
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
    current_user = Depends(get_current_user)
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
# PARTICIPANT ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/participants")
async def add_participant(
    room_id: int,
    data: ParticipantAdd,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a participant to a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')
    User = _models.get('User')

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

    # Send invite email if send_invite is True
    if data.send_invite and data.email:
        # Get host info
        host = db.query(User).filter(User.id == room.host_user_id).first() if User else None
        host_name = host.name if host and hasattr(host, 'name') else current_user.name if hasattr(current_user, 'name') else "Host"

        # Build join URL
        import os
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
    current_user = Depends(get_current_user)
):
    """Update a participant's settings."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    # SECURITY: Verify user is the host of this meeting
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

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    # SECURITY: Verify user is the host of this meeting
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


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    data: MeetingTemplateUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update an existing meeting template."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Update only provided fields
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected and hasattr(template, field):
            setattr(template, field, value)

    db.commit()
    db.refresh(template)

    return {
        "success": True,
        "template": {
            "id": template.id,
            "template_key": template.template_key,
            "template_name": template.template_name,
            "description": template.description,
            "default_duration_minutes": template.default_duration_minutes,
            "recording_enabled": template.recording_enabled,
            "ai_assistant_enabled": template.ai_assistant_enabled,
            "color": template.color,
            "icon": template.icon
        }
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a meeting template."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Prevent deletion of system templates
    if template.is_system_template:
        raise HTTPException(status_code=400, detail="Cannot delete system templates")

    db.delete(template)
    db.commit()

    return {"success": True, "message": "Template deleted"}


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

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingRecording = _models.get('MeetingRecording')

    # SECURITY: Verify user has access to this room
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
    current_user = Depends(get_current_user)
):
    """Stop recording a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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

    # Trigger recording processing in background
    background_tasks.add_task(process_recording, recording_id)

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

    # Trigger AI analysis in background
    background_tasks.add_task(run_ai_analysis, room_id, data.analysis_types)

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
    password: Optional[str] = Query(None),
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

    # Verify password for password-protected rooms
    if room.password_protected and room.room_password:
        if not password:
            raise HTTPException(status_code=403, detail="This meeting requires a password")
        # Verify against hashed password if pwd_context is available, otherwise plain compare
        if _pwd_context:
            if not _pwd_context.verify(password, room.room_password):
                raise HTTPException(status_code=403, detail="Incorrect meeting password")
        else:
            if password != room.room_password:
                raise HTTPException(status_code=403, detail="Incorrect meeting password")

    return {
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

    if not await _validate_twilio_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

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
    if not await _validate_twilio_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

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
        return {"error": "Internal processing error"}


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

    # SECURITY: Verify user has access to this recording
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
    current_user = Depends(get_current_user)
):
    """Get AI analysis for a recording."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    # SECURITY: Verify user has access to this recording
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
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CONVERSATION ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/analytics")
async def get_recording_analytics(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get analytics for all participants in a recording"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    # SECURITY: Verify user has access to this recording
    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    ParticipantAnalytics = _models.get('ParticipantAnalytics')
    MeetingParticipant = _models.get('MeetingParticipant')
    CoachingRecommendation = _models.get('CoachingRecommendation')

    if not ParticipantAnalytics:
        raise HTTPException(status_code=500, detail="ParticipantAnalytics model not found")

    analytics_records = db.query(ParticipantAnalytics).filter(
        ParticipantAnalytics.recording_id == recording_id
    ).all()

    result = []
    for a in analytics_records:
        # Get participant info
        participant = None
        if MeetingParticipant:
            participant = db.query(MeetingParticipant).filter(
                MeetingParticipant.id == a.participant_id
            ).first()

        # Get coaching recommendations
        recommendations = []
        if CoachingRecommendation:
            recs = db.query(CoachingRecommendation).filter(
                CoachingRecommendation.analytics_id == a.id
            ).all()
            recommendations = [
                {
                    "category": rec.category,
                    "recommendation": rec.recommendation,
                    "priority": rec.priority,
                    "evidence": rec.evidence
                }
                for rec in recs
            ]

        result.append({
            "id": a.id,
            "participant_id": a.participant_id,
            "participant_name": participant.display_name if participant else None,
            "talk_time_seconds": a.talk_time_seconds,
            "listen_time_seconds": a.listen_time_seconds,
            "talk_listen_ratio": a.talk_listen_ratio,
            "longest_monologue_seconds": a.longest_monologue_seconds,
            "interruption_count": a.interruption_count,
            "question_count": a.question_count,
            "filler_word_count": a.filler_word_count,
            "speaking_pace_wpm": a.speaking_pace_wpm,
            "sentiment_positive_pct": a.sentiment_positive_pct,
            "sentiment_negative_pct": a.sentiment_negative_pct,
            "sentiment_neutral_pct": a.sentiment_neutral_pct,
            "engagement_score": a.engagement_score,
            "coaching_recommendations": recommendations
        })

    return {"analytics": result}


@router.post("/recordings/{recording_id}/analyze")
async def analyze_recording(
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Trigger analytics processing for a recording"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    MeetingRecording = _models.get('MeetingRecording')
    RecordingTranscript = _models.get('RecordingTranscript')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Check if transcript exists
    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id,
        RecordingTranscript.status == "completed"
    ).first()

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not ready. Please wait for transcription to complete.")

    # Trigger analysis in background
    background_tasks.add_task(
        process_recording_analytics,
        recording_id,
        recording.meeting_id
    )

    return {"success": True, "message": "Analytics processing started", "recording_id": recording_id}


@router.get("/analytics/user/{user_id}")
async def get_user_analytics(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get aggregate analytics for a user across all meetings"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.coaching_service import get_coaching_service
        coaching_service = get_coaching_service()

        result = await coaching_service.get_user_coaching_summary(
            user_id=user_id,
            db=db,
            models=_models,
            days=days
        )

        return result

    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/me")
async def get_my_analytics(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get aggregate analytics for the current user"""
    return await get_user_analytics(
        user_id=current_user.id,
        days=days,
        db=db,
        current_user=current_user
    )


@router.get("/analytics/team")
async def get_team_analytics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get team-wide analytics for managers"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ParticipantAnalytics = _models.get('ParticipantAnalytics')
    MeetingParticipant = _models.get('MeetingParticipant')

    if not all([ParticipantAnalytics, MeetingParticipant]):
        raise HTTPException(status_code=500, detail="Required models not available")

    # Get team_id from current user (if available)
    team_id = getattr(current_user, 'team_id', None)
    organization_id = getattr(current_user, 'organization_id', None)

    # For now, get all analytics (in production, filter by team)
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=30)

    analytics_records = db.query(ParticipantAnalytics).filter(
        ParticipantAnalytics.created_at >= cutoff_date
    ).all()

    if not analytics_records:
        return {
            "total_meetings": 0,
            "team_size": 0,
            "avg_engagement_score": 0,
            "top_performers": [],
            "coaching_priorities": []
        }

    # Group by participant/user
    user_analytics = {}
    for a in analytics_records:
        participant = db.query(MeetingParticipant).filter(
            MeetingParticipant.id == a.participant_id
        ).first()

        if participant and participant.user_id:
            if participant.user_id not in user_analytics:
                user_analytics[participant.user_id] = {
                    "name": participant.display_name,
                    "meetings": [],
                    "total_engagement": 0
                }
            user_analytics[participant.user_id]["meetings"].append(a)
            user_analytics[participant.user_id]["total_engagement"] += (a.engagement_score or 0)

    # Calculate per-user metrics
    user_metrics = []
    for user_id, data in user_analytics.items():
        meeting_count = len(data["meetings"])
        if meeting_count > 0:
            avg_engagement = data["total_engagement"] / meeting_count
            avg_talk_ratio = sum(m.talk_listen_ratio or 0 for m in data["meetings"]) / meeting_count
            avg_questions = sum(m.question_count or 0 for m in data["meetings"]) / meeting_count

            user_metrics.append({
                "user_id": user_id,
                "name": data["name"],
                "meetings": meeting_count,
                "avg_engagement": round(avg_engagement, 2),
                "avg_talk_ratio": round(avg_talk_ratio, 2),
                "avg_questions": round(avg_questions, 1)
            })

    # Sort by engagement
    top_performers = sorted(user_metrics, key=lambda x: x["avg_engagement"], reverse=True)[:5]

    return {
        "total_meetings": len(set(a.recording_id for a in analytics_records)),
        "team_size": len(user_analytics),
        "avg_engagement_score": round(
            sum(a.engagement_score or 0 for a in analytics_records) / len(analytics_records), 2
        ) if analytics_records else 0,
        "top_performers": top_performers,
        "period_days": 30
    }


async def process_recording_analytics(recording_id: int, meeting_id: int):
    """Background task to process analytics for a recording"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.analytics_service import get_analytics_service
        from uvip.coaching_service import get_coaching_service

        analytics_service = get_analytics_service()
        coaching_service = get_coaching_service()

        # Analyze all participants
        analytics_results = await analytics_service.analyze_all_participants(
            recording_id=recording_id,
            db=db,
            models=_models
        )

        # Generate coaching for each participant
        RecordingTranscript = _models.get('RecordingTranscript')
        transcript = db.query(RecordingTranscript).filter(
            RecordingTranscript.recording_id == recording_id
        ).first()

        transcript_segments = transcript.transcript_json if transcript else []

        for analytics in analytics_results:
            try:
                await coaching_service.generate_coaching(
                    analytics=analytics,
                    transcript_segments=transcript_segments,
                    db=db,
                    models=_models
                )
            except Exception as e:
                logger.error(f"Error generating coaching for analytics {analytics.get('id')}: {e}")

        logger.info(f"Analytics processing completed for recording {recording_id}")

    except Exception as e:
        logger.error(f"Error processing analytics for recording {recording_id}: {e}")
    finally:
        db.close()


# ============================================================================
# MORTGAGE INTELLIGENCE ENDPOINTS
# ============================================================================

@router.get("/recordings/{recording_id}/intelligence")
async def get_mortgage_intelligence(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get mortgage-specific intelligence from a recording"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    # SECURITY: Verify user has access to this recording
    if not verify_recording_access(recording_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")

    MortgageIntelligence = _models.get('MortgageIntelligence')
    if not MortgageIntelligence:
        raise HTTPException(status_code=500, detail="MortgageIntelligence model not found")

    intelligence = db.query(MortgageIntelligence).filter(
        MortgageIntelligence.recording_id == recording_id
    ).first()

    if not intelligence:
        raise HTTPException(status_code=404, detail="Intelligence not available for this recording")

    return {
        "id": intelligence.id,
        "recording_id": intelligence.recording_id,
        "borrower_concerns": intelligence.borrower_concerns or [],
        "compliance_risks": intelligence.compliance_risks or [],
        "competitor_mentions": intelligence.competitor_mentions or {},
        "objections": intelligence.objections or [],
        "explanation_effectiveness": intelligence.explanation_effectiveness or {},
        "loan_details": intelligence.loan_details or {},
        "next_steps_clarity": intelligence.next_steps_clarity or {},
        "overall_risk_score": intelligence.overall_risk_score,
        "priority_flags": intelligence.priority_flags or [],
        "created_at": intelligence.created_at.isoformat() if intelligence.created_at else None
    }


@router.post("/recordings/{recording_id}/intelligence/analyze")
async def analyze_mortgage_intelligence(
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Trigger mortgage intelligence analysis for a recording"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    MeetingRecording = _models.get('MeetingRecording')
    RecordingTranscript = _models.get('RecordingTranscript')

    recording = db.query(MeetingRecording).filter(MeetingRecording.id == recording_id).first()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Check if transcript exists
    transcript = db.query(RecordingTranscript).filter(
        RecordingTranscript.recording_id == recording_id,
        RecordingTranscript.status == "completed"
    ).first()

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not ready. Please wait for transcription to complete.")

    # Trigger analysis in background
    background_tasks.add_task(
        process_mortgage_intelligence,
        recording_id
    )

    return {"success": True, "message": "Mortgage intelligence analysis started", "recording_id": recording_id}


@router.get("/intelligence/summary")
async def get_intelligence_summary(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get summary of mortgage intelligence across all recordings for a user"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    MortgageIntelligence = _models.get('MortgageIntelligence')
    MeetingRecording = _models.get('MeetingRecording')
    VideoMeetingRoom = _models.get('VideoMeetingRoom')

    if not all([MortgageIntelligence, MeetingRecording, VideoMeetingRoom]):
        raise HTTPException(status_code=500, detail="Required models not available")

    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get recordings for this user
    recordings = db.query(MeetingRecording).join(
        VideoMeetingRoom,
        MeetingRecording.meeting_id == VideoMeetingRoom.id
    ).filter(
        VideoMeetingRoom.host_user_id == current_user.id,
        MeetingRecording.created_at >= cutoff_date
    ).all()

    recording_ids = [r.id for r in recordings]

    if not recording_ids:
        return {
            "meetings_analyzed": 0,
            "period_days": days,
            "message": "No recordings found for this period"
        }

    # Get intelligence records
    intel_records = db.query(MortgageIntelligence).filter(
        MortgageIntelligence.recording_id.in_(recording_ids)
    ).all()

    if not intel_records:
        return {
            "meetings_analyzed": len(recordings),
            "intelligence_processed": 0,
            "period_days": days,
            "message": "No intelligence analysis available yet"
        }

    # Aggregate statistics
    total_concerns = 0
    concern_types = {}
    total_compliance_risks = 0
    compliance_types = {}
    total_competitor_mentions = 0
    competitors_mentioned = {}
    avg_risk_score = 0
    total_objections = 0
    objections_handled_well = 0

    for intel in intel_records:
        # Concerns
        concerns = intel.borrower_concerns or []
        total_concerns += len(concerns)
        for concern in concerns:
            ctype = concern.get("concern_type", "unknown")
            concern_types[ctype] = concern_types.get(ctype, 0) + 1

        # Compliance
        risks = intel.compliance_risks or []
        total_compliance_risks += len(risks)
        for risk in risks:
            rtype = risk.get("risk_type", "unknown")
            compliance_types[rtype] = compliance_types.get(rtype, 0) + 1

        # Competitors
        comp_data = intel.competitor_mentions or {}
        summary = comp_data.get("summary", {})
        for comp, data in summary.items():
            total_competitor_mentions += data.get("count", 0)
            competitors_mentioned[comp] = competitors_mentioned.get(comp, 0) + data.get("count", 0)

        # Risk score
        avg_risk_score += (intel.overall_risk_score or 0)

        # Objections
        objections = intel.objections or []
        total_objections += len(objections)
        objections_handled_well += sum(1 for o in objections if o.get("handled_well"))

    num_records = len(intel_records)
    avg_risk_score = avg_risk_score / num_records if num_records > 0 else 0

    return {
        "meetings_analyzed": len(recordings),
        "intelligence_processed": num_records,
        "period_days": days,
        "summary": {
            "total_borrower_concerns": total_concerns,
            "concern_breakdown": concern_types,
            "total_compliance_flags": total_compliance_risks,
            "compliance_breakdown": compliance_types,
            "total_competitor_mentions": total_competitor_mentions,
            "competitors_mentioned": competitors_mentioned,
            "avg_risk_score": round(avg_risk_score, 2),
            "total_objections": total_objections,
            "objections_handled_well_pct": round(
                (objections_handled_well / total_objections * 100) if total_objections > 0 else 100, 1
            )
        },
        "recommendations": _generate_summary_recommendations(
            concern_types, compliance_types, avg_risk_score, total_objections, objections_handled_well
        )
    }


def _generate_summary_recommendations(
    concern_types: Dict,
    compliance_types: Dict,
    avg_risk_score: float,
    total_objections: int,
    objections_handled_well: int
) -> List[Dict]:
    """Generate recommendations based on aggregated intelligence"""

    recommendations = []

    # High rate anxiety across calls
    if concern_types.get("rate_anxiety", 0) > 3:
        recommendations.append({
            "category": "rate_discussion",
            "priority": "high",
            "recommendation": "Rate anxiety is common in your calls. Proactively explain rate lock options and market context early in conversations."
        })

    # Competition concerns
    if concern_types.get("competing_offers", 0) > 2:
        recommendations.append({
            "category": "competitive",
            "priority": "high",
            "recommendation": "Borrowers frequently mention other lenders. Focus on relationship value and service quality, not just rates."
        })

    # Compliance issues
    if len(compliance_types) > 0:
        recommendations.append({
            "category": "compliance",
            "priority": "critical",
            "recommendation": f"Compliance flags detected. Review recordings for potential steering or pressure issues."
        })

    # Objection handling
    if total_objections > 0:
        handling_rate = objections_handled_well / total_objections
        if handling_rate < 0.7:
            recommendations.append({
                "category": "objection_handling",
                "priority": "medium",
                "recommendation": "Objection handling could improve. Practice empathetic listening and the 'Feel, Felt, Found' technique."
            })

    # Overall risk
    if avg_risk_score > 0.3:
        recommendations.append({
            "category": "general",
            "priority": "high",
            "recommendation": "Your average call risk score is elevated. Review recent recordings and focus on clear communication and compliance."
        })

    return recommendations


async def process_mortgage_intelligence(recording_id: int):
    """Background task to process mortgage intelligence for a recording"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.mortgage_intelligence_service import get_mortgage_intelligence_service

        intel_service = get_mortgage_intelligence_service()

        RecordingTranscript = _models.get('RecordingTranscript')

        # Get transcript
        transcript = db.query(RecordingTranscript).filter(
            RecordingTranscript.recording_id == recording_id
        ).first()

        if not transcript:
            logger.error(f"No transcript found for recording {recording_id}")
            return

        full_transcript = transcript.full_transcript or ""
        transcript_segments = transcript.transcript_json or []

        # Run intelligence analysis
        intelligence = await intel_service.analyze_mortgage_intelligence(
            recording_id=recording_id,
            transcript_text=full_transcript,
            transcript_segments=transcript_segments,
            db=db,
            models=_models
        )

        logger.info(f"Mortgage intelligence processing completed for recording {recording_id}")

    except Exception as e:
        logger.error(f"Error processing mortgage intelligence for recording {recording_id}: {e}")
    finally:
        db.close()


# ============================================================================
# MANAGER DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/analytics/manager/dashboard")
async def get_manager_dashboard(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get comprehensive manager dashboard with team performance metrics"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        # Get team member IDs - for now, get all users in the org
        # In production, this would filter by manager's direct reports
        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            # Fallback: just use current user
            team_member_ids = [current_user.id]

        dashboard_service = get_manager_dashboard_service(db, _models)

        result = await dashboard_service.get_team_overview(
            team_member_ids=team_member_ids,
            days=days
        )

        return result

    except Exception as e:
        logger.error(f"Error getting manager dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/manager/compare/{user_id}")
async def compare_user_to_team(
    user_id: int,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Compare individual user performance against team averages"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        # Get team member IDs
        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            team_member_ids = [current_user.id]

        # Verify user is in team
        if user_id not in team_member_ids:
            raise HTTPException(status_code=403, detail="User not in your team")

        dashboard_service = get_manager_dashboard_service(db, _models)

        result = await dashboard_service.get_individual_comparison(
            user_id=user_id,
            team_member_ids=team_member_ids,
            days=days
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing user to team: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/manager/leaderboard")
async def get_team_leaderboard(
    metric: str = Query("engagement_score", regex="^(engagement_score|question_count|positive_sentiment|talk_listen_ratio)$"),
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get team leaderboard for specific metrics"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.manager_dashboard_service import get_manager_dashboard_service

        # Get team member IDs
        User = _models.get('User')
        organization_id = getattr(current_user, 'organization_id', None)

        team_member_ids = []
        if User and organization_id:
            team_members = db.query(User).filter(
                User.organization_id == organization_id
            ).all()
            team_member_ids = [m.id for m in team_members]
        else:
            team_member_ids = [current_user.id]

        dashboard_service = get_manager_dashboard_service(db, _models)

        leaderboard = await dashboard_service.get_leaderboard(
            team_member_ids=team_member_ids,
            days=days,
            metric=metric
        )

        return {
            "metric": metric,
            "period_days": days,
            "leaderboard": leaderboard
        }

    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TABLE SETUP / MIGRATION ENDPOINTS
# ============================================================================

@router.post("/setup-consent-fields")
async def setup_consent_fields(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add recording consent columns to meeting_recordings and meeting_participants tables."""
    _require_admin(current_user)
    try:
        alter_statements = [
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_obtained BOOLEAN DEFAULT FALSE",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_type VARCHAR(20)",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_state_code VARCHAR(2)",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS disclosure_script_shown TEXT",
            "ALTER TABLE meeting_recordings ADD COLUMN IF NOT EXISTS consent_obtained_at TIMESTAMP",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_given BOOLEAN DEFAULT FALSE",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_at TIMESTAMP",
            "ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS recording_consent_method VARCHAR(20)",
        ]

        from sqlalchemy import text
        for stmt in alter_statements:
            try:
                db.execute(text(stmt))
            except Exception as e:
                logger.warning(f"Migration statement skipped: {e}")

        db.commit()
        return {"success": True, "message": "Consent fields migration completed"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error setting up consent fields: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/org-settings/setup")
async def setup_org_video_settings_table(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create the organization_video_settings table."""
    _require_admin(current_user)
    try:
        from sqlalchemy import text
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS organization_video_settings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER UNIQUE NOT NULL,
                recording_allowed BOOLEAN DEFAULT TRUE,
                recording_consent_required BOOLEAN DEFAULT TRUE,
                default_consent_type VARCHAR(20) DEFAULT 'one_party',
                default_waiting_room BOOLEAN DEFAULT TRUE,
                max_participants INTEGER DEFAULT 50,
                allowed_providers JSON DEFAULT '["internal", "zoom", "teams"]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.commit()
        return {"success": True, "message": "organization_video_settings table created"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating org video settings table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# RECORDING CONSENT ENDPOINTS
# ============================================================================

class StartRecordingRequest(BaseModel):
    consent_type: Optional[str] = None  # "all_party" or "one_party"
    state_code: Optional[str] = None
    disclosure_script: Optional[str] = None


class RecordingConsentRequest(BaseModel):
    consent_given: bool
    method: str = "dialog_click"  # "dialog_click", "verbal", "implied"


@router.post("/rooms/{room_id}/recordings/start-with-consent")
async def start_recording_with_consent(
    room_id: int,
    data: StartRecordingRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start recording with consent metadata tracked."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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

    # For all-party consent states, check that all active participants have consented
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
    current_user = Depends(get_current_user)
):
    """Submit recording consent for a participant."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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
    current_user = Depends(get_current_user)
):
    """Get recording consent status for all active participants in a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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
# ORGANIZATION VIDEO SETTINGS ENDPOINTS
# ============================================================================

class OrgVideoSettingsUpdate(BaseModel):
    recording_allowed: Optional[bool] = None
    recording_consent_required: Optional[bool] = None
    default_consent_type: Optional[str] = None
    default_waiting_room: Optional[bool] = None
    max_participants: Optional[int] = None
    allowed_providers: Optional[List[MeetingProvider]] = None

    @validator('default_consent_type')
    def validate_consent_type(cls, v):
        if v is not None and v not in ('one_party', 'two_party', 'all_party'):
            raise ValueError("consent_type must be one_party, two_party, or all_party")
        return v


@router.get("/org-settings")
async def get_org_video_settings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get organization video meeting settings."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    OrganizationVideoSettings = _models.get('OrganizationVideoSettings')
    if not OrganizationVideoSettings:
        raise HTTPException(status_code=500, detail="OrganizationVideoSettings model not found")

    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        return {
            "settings": None,
            "message": "No organization associated with user"
        }

    settings = db.query(OrganizationVideoSettings).filter(
        OrganizationVideoSettings.organization_id == org_id
    ).first()

    if not settings:
        return {
            "settings": {
                "recording_allowed": True,
                "recording_consent_required": True,
                "default_consent_type": "one_party",
                "default_waiting_room": True,
                "max_participants": 50,
                "allowed_providers": ["internal", "zoom", "teams"]
            },
            "is_default": True
        }

    return {
        "settings": {
            "recording_allowed": settings.recording_allowed,
            "recording_consent_required": settings.recording_consent_required,
            "default_consent_type": settings.default_consent_type,
            "default_waiting_room": settings.default_waiting_room,
            "max_participants": settings.max_participants,
            "allowed_providers": settings.allowed_providers or ["internal", "zoom", "teams"]
        },
        "is_default": False
    }


@router.put("/org-settings")
async def update_org_video_settings(
    data: OrgVideoSettingsUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update organization video meeting settings."""
    _require_admin(current_user)
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    OrganizationVideoSettings = _models.get('OrganizationVideoSettings')
    if not OrganizationVideoSettings:
        raise HTTPException(status_code=500, detail="OrganizationVideoSettings model not found")

    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")

    settings = db.query(OrganizationVideoSettings).filter(
        OrganizationVideoSettings.organization_id == org_id
    ).first()

    if not settings:
        settings = OrganizationVideoSettings(organization_id=org_id)
        db.add(settings)

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and field not in _protected:
            setattr(settings, field, value)

    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)

    return {
        "success": True,
        "settings": {
            "recording_allowed": settings.recording_allowed,
            "recording_consent_required": settings.recording_consent_required,
            "default_consent_type": settings.default_consent_type,
            "default_waiting_room": settings.default_waiting_room,
            "max_participants": settings.max_participants,
            "allowed_providers": settings.allowed_providers
        }
    }


# ============================================================================
# SFU (SELECTIVE FORWARDING UNIT) ENDPOINTS
# ============================================================================

@router.get("/sfu/status")
async def get_sfu_status():
    """Check if SFU (LiveKit) is available and configured."""
    try:
        from services.media.sfu_service import sfu_service
        return {
            "enabled": sfu_service.enabled,
            "participant_threshold": 4,
            "provider": "livekit" if sfu_service.enabled else None
        }
    except ImportError:
        return {
            "enabled": False,
            "participant_threshold": 4,
            "provider": None
        }


@router.post("/rooms/{room_id}/sfu/token")
async def get_sfu_token(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate a LiveKit token for a participant to join via SFU."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        from services.media.sfu_service import sfu_service
        if not sfu_service.enabled:
            raise HTTPException(status_code=503, detail="SFU service not configured")

        is_host = room.host_user_id == current_user.id
        display_name = getattr(current_user, 'full_name', None) or getattr(current_user, 'email', 'Participant')

        token = sfu_service.generate_token(
            room_name=room.room_code,
            participant_identity=str(current_user.id),
            is_host=is_host
        )

        return {
            "token": token,
            "room_name": room.room_code,
            "livekit_url": sfu_service.livekit_url,
            "is_host": is_host,
            "display_name": display_name
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="SFU service not installed")


@router.post("/rooms/{room_id}/sfu/create")
async def create_sfu_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a LiveKit room for SFU-mode meetings."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can create SFU rooms")

    try:
        from services.media.sfu_service import sfu_service
        if not sfu_service.enabled:
            raise HTTPException(status_code=503, detail="SFU service not configured")

        result = sfu_service.create_room(
            room_name=room.room_code,
            max_participants=room.max_participants or 50
        )

        if result is None:
            raise HTTPException(status_code=500, detail="Failed to create SFU room")

        return {
            "success": True,
            "sfu_room": result,
            "room_code": room.room_code
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="SFU service not installed")


@router.get("/rooms/{room_id}/sfu/participants")
async def get_sfu_participants(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List participants connected via SFU."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        from services.media.sfu_service import sfu_service
        if not sfu_service.enabled:
            return {"participants": [], "count": 0}

        participants = sfu_service.list_participants(room.room_code)
        return {
            "participants": participants or [],
            "count": len(participants) if participants else 0
        }
    except ImportError:
        return {"participants": [], "count": 0}


@router.get("/rooms/{room_id}/mode")
async def get_meeting_mode(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Determine whether to use mesh (P2P) or SFU mode based on participant count."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    active_count = db.query(MeetingParticipant).filter(
        MeetingParticipant.meeting_id == room_id,
        MeetingParticipant.status == "joined"
    ).count()

    sfu_available = False
    try:
        from services.media.sfu_service import sfu_service
        sfu_available = sfu_service.enabled
    except ImportError:
        pass

    should_use_sfu = active_count > 4 and sfu_available

    return {
        "mode": "sfu" if should_use_sfu else "mesh",
        "participant_count": active_count,
        "sfu_available": sfu_available,
        "threshold": 4,
        "room_code": room.room_code
    }


# ============================================================================
# BREAKOUT ROOM ENDPOINTS
# ============================================================================

class BreakoutRoomCreate(BaseModel):
    room_name: str
    max_participants: Optional[int] = 10
    duration_limit_minutes: Optional[int] = None


@router.post("/rooms/{room_id}/breakout-rooms")
async def create_breakout_room(
    room_id: int,
    data: BreakoutRoomCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a breakout room within a meeting (host only)."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    BreakoutRoom = _models.get('BreakoutRoom')

    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can create breakout rooms")

    # Get next room index
    existing_count = db.query(BreakoutRoom).filter(
        BreakoutRoom.meeting_id == room_id,
        BreakoutRoom.status == "open"
    ).count()

    breakout = BreakoutRoom(
        meeting_id=room_id,
        room_name=data.room_name,
        room_index=existing_count,
        max_participants=data.max_participants,
        duration_limit_minutes=data.duration_limit_minutes,
        participant_ids=[],
        created_by=current_user.id
    )
    db.add(breakout)
    db.commit()
    db.refresh(breakout)

    return {
        "success": True,
        "breakout_room": {
            "id": breakout.id,
            "room_name": breakout.room_name,
            "room_index": breakout.room_index,
            "max_participants": breakout.max_participants,
            "duration_limit_minutes": breakout.duration_limit_minutes,
            "participant_ids": breakout.participant_ids,
            "status": breakout.status
        }
    }


@router.get("/rooms/{room_id}/breakout-rooms")
async def list_breakout_rooms(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all breakout rooms for a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    BreakoutRoom = _models.get('BreakoutRoom')
    if not BreakoutRoom:
        return {"breakout_rooms": []}

    rooms = db.query(BreakoutRoom).filter(
        BreakoutRoom.meeting_id == room_id,
        BreakoutRoom.status == "open"
    ).order_by(BreakoutRoom.room_index).all()

    return {
        "breakout_rooms": [
            {
                "id": r.id,
                "room_name": r.room_name,
                "room_index": r.room_index,
                "max_participants": r.max_participants,
                "participant_ids": r.participant_ids or [],
                "participant_count": len(r.participant_ids or []),
                "status": r.status
            }
            for r in rooms
        ]
    }


@router.post("/rooms/{room_id}/breakout-rooms/{breakout_id}/join")
async def join_breakout_room(
    room_id: int,
    breakout_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Join a breakout room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    BreakoutRoom = _models.get('BreakoutRoom')
    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    breakout = db.query(BreakoutRoom).filter(
        BreakoutRoom.id == breakout_id,
        BreakoutRoom.meeting_id == room_id,
        BreakoutRoom.status == "open"
    ).first()

    if not breakout:
        raise HTTPException(status_code=404, detail="Breakout room not found")

    participant_ids = breakout.participant_ids or []
    user_id_str = str(current_user.id)

    if len(participant_ids) >= (breakout.max_participants or 10):
        raise HTTPException(status_code=400, detail="Breakout room is full")

    if user_id_str not in participant_ids:
        participant_ids.append(user_id_str)
        breakout.participant_ids = participant_ids
        db.commit()

    return {
        "success": True,
        "breakout_room_id": breakout_id,
        "participant_count": len(participant_ids)
    }


@router.post("/rooms/{room_id}/breakout-rooms/{breakout_id}/leave")
async def leave_breakout_room(
    room_id: int,
    breakout_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Leave a breakout room."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    BreakoutRoom = _models.get('BreakoutRoom')
    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    breakout = db.query(BreakoutRoom).filter(
        BreakoutRoom.id == breakout_id,
        BreakoutRoom.meeting_id == room_id
    ).first()

    if not breakout:
        raise HTTPException(status_code=404, detail="Breakout room not found")

    participant_ids = breakout.participant_ids or []
    user_id_str = str(current_user.id)

    if user_id_str in participant_ids:
        participant_ids.remove(user_id_str)
        breakout.participant_ids = participant_ids
        db.commit()

    return {"success": True, "breakout_room_id": breakout_id}


@router.post("/rooms/{room_id}/breakout-rooms/{breakout_id}/close")
async def close_breakout_room(
    room_id: int,
    breakout_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Close a breakout room (host only)."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    BreakoutRoom = _models.get('BreakoutRoom')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can close breakout rooms")

    breakout = db.query(BreakoutRoom).filter(
        BreakoutRoom.id == breakout_id,
        BreakoutRoom.meeting_id == room_id
    ).first()

    if not breakout:
        raise HTTPException(status_code=404, detail="Breakout room not found")

    breakout.status = "closed"
    breakout.closed_at = datetime.utcnow()
    db.commit()

    return {"success": True, "breakout_room_id": breakout_id, "status": "closed"}


@router.post("/breakout-rooms/setup")
async def setup_breakout_rooms_table(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create the breakout_rooms table if it doesn't exist."""
    _require_admin(current_user)
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    BreakoutRoom = _models.get('BreakoutRoom')
    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    try:
        from database import engine
        BreakoutRoom.__table__.create(engine, checkfirst=True)
        return {"success": True, "message": "breakout_rooms table ready"}
    except Exception as e:
        logger.error(f"Error creating breakout_rooms table: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TRANSCRIPTION ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/recordings/{recording_id}/transcribe")
async def start_transcription(
    room_id: int,
    recording_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start transcription of a meeting recording."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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

    # Check if transcript already exists
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

    # Create transcript record
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
    current_user = Depends(get_current_user)
):
    """Get the transcript for a recording."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

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


# ============================================================================
# CALENDAR INVITE ENDPOINT
# ============================================================================

@router.post("/rooms/{room_id}/calendar-invite")
async def generate_calendar_invite(
    room_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate an ICS calendar invite for a meeting."""
    if _models is None:
        raise HTTPException(status_code=500, detail="Video meeting models not initialized")

    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    MeetingParticipant = _models.get('MeetingParticipant')

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        from services.calendar_invite_service import calendar_invite_service

        # Get participants as attendee list
        participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == room_id
        ).all()

        attendees = [
            {"email": p.email or "", "name": p.display_name or ""}
            for p in participants if p.email
        ]

        ics_content = calendar_invite_service.create_meeting_invite(
            room=room,
            host_user=current_user,
            attendee_list=attendees,
            base_url="https://app.perenniaai.com"
        )

        from fastapi.responses import Response
        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="meeting-{room.room_code}.ics"'
            }
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Calendar invite service not available")
