"""
UVIP - Video Meeting Realtime Routes
Extracted from video_meeting_crud_routes.py

Handles:
- Breakout rooms (create, list, join, leave, close)
- SFU endpoints (status, token, create, participants)
- Meeting mode detection (mesh vs SFU)
- Phone dial-out for meetings
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from video_meeting_shared import (
    get_db, get_current_user, get_models,
    verify_host_permission,
)
from video_meeting_schemas import BreakoutRoomCreate

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PHONE DIAL-OUT FOR MEETINGS
# ============================================================================

@router.post("/rooms/{room_code}/dial-participant")
async def dial_participant(
    room_code: str,
    phone_number: str = Body(...),
    participant_name: str = Body(default="Participant"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Dial out to a participant and connect them to the meeting."""
    _models = get_models()
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

        from_phone = recording_service.from_number

        call_sid = await recording_service.start_recorded_call(
            meeting_room_id=room_code,
            participant_phone=phone_number,
            from_phone=from_phone,
            participant_name=participant_name
        )

        if not call_sid:
            raise HTTPException(status_code=500, detail="Failed to initiate call")

        if MeetingParticipant:
            participant = MeetingParticipant(
                meeting_id=room.id,
                display_name=participant_name,
                role="participant",
                status="invited",
                device_type="phone"
            )
            participant.connection_quality = call_sid
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
# BREAKOUT ROOM ENDPOINTS
# ============================================================================

@router.post("/rooms/{room_id}/breakout-rooms")
async def create_breakout_room(
    room_id: int,
    data: BreakoutRoomCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a breakout room within a meeting (host only)."""
    _models = get_models()
    VideoMeetingRoom = _models.get('VideoMeetingRoom')
    BreakoutRoom = _models.get('BreakoutRoom')

    if not BreakoutRoom:
        raise HTTPException(status_code=500, detail="BreakoutRoom model not found")

    room = db.query(VideoMeetingRoom).filter(VideoMeetingRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can create breakout rooms")

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
    current_user=Depends(get_current_user)
):
    """List all breakout rooms for a meeting."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """Join a breakout room."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """Leave a breakout room."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """Close a breakout room (host only)."""
    _models = get_models()
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
    breakout.closed_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "breakout_room_id": breakout_id, "status": "closed"}


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
    current_user=Depends(get_current_user)
):
    """Generate a LiveKit token for a participant to join via SFU."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """Create a LiveKit room for SFU-mode meetings."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """List participants connected via SFU."""
    _models = get_models()
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
    current_user=Depends(get_current_user)
):
    """Determine whether to use mesh (P2P) or SFU mode based on participant count."""
    _models = get_models()
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
