"""
Conference Calling Routes
Implements multi-party conference calls for 10+ participants
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
from enum import Enum
import logging
import json
import os
import secrets
import asyncio

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from middleware.webhook_verification import require_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conferences", tags=["conferences"])


def safe_isoformat(dt_value) -> Optional[str]:
    """Safely convert datetime to ISO format string, handling both datetime objects and strings"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        return dt_value  # Already a string (SQLite returns strings)
    if hasattr(dt_value, 'isoformat'):
        return dt_value.isoformat()
    return str(dt_value)


from auth.dependencies import get_current_user_flexible  # dedup
def get_telephony_provider():
    """Get telephony provider"""
    from telephony.provider import get_telephony_provider as _get_provider
    return _get_provider()


# ============================================================================
# MODELS
# ============================================================================

class ParticipantRole(str, Enum):
    HOST = "host"
    MODERATOR = "moderator"
    PARTICIPANT = "participant"
    LISTENER = "listener"


class ConferenceCreate(BaseModel):
    """Create conference room"""
    room_name: str
    friendly_name: Optional[str] = None
    max_participants: int = 50
    start_on_enter: bool = True  # Start when first participant joins
    end_on_exit: bool = False  # End when host leaves
    mute_on_entry: bool = False  # Mute participants on entry
    record_conference: bool = False
    pin_required: bool = False
    host_pin: Optional[str] = None  # Auto-generated if not provided
    participant_pin: Optional[str] = None


class ConferenceUpdate(BaseModel):
    """Update conference room"""
    friendly_name: Optional[str] = None
    max_participants: Optional[int] = None
    start_on_enter: Optional[bool] = None
    end_on_exit: Optional[bool] = None
    mute_on_entry: Optional[bool] = None
    record_conference: Optional[bool] = None
    pin_required: Optional[bool] = None
    host_pin: Optional[str] = None
    participant_pin: Optional[str] = None
    is_active: Optional[bool] = None


class AddParticipantRequest(BaseModel):
    """Add participant to conference"""
    phone: Optional[str] = None  # Dial out to phone
    user_id: Optional[int] = None  # Dial out to user
    role: ParticipantRole = ParticipantRole.PARTICIPANT
    muted: bool = False
    announce_name: Optional[str] = None


class ParticipantAction(BaseModel):
    """Action on participant"""
    action: str  # mute, unmute, hold, unhold, remove


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_pin(length: int = 6) -> str:
    """Generate a numeric PIN"""
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def format_phone(phone: str) -> str:
    """Format phone number to E.164"""
    import re
    phone = re.sub(r'[^\d+]', '', phone)
    if len(phone) == 10:
        return f"+1{phone}"
    elif not phone.startswith("+"):
        return f"+{phone}"
    return phone


def get_user_phone(db: Session, user_id: int) -> Optional[str]:
    """Get user's phone number"""
    result = db.execute(text("""
        SELECT phone, work_phone, mobile_phone FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    if result:
        return result.mobile_phone or result.work_phone or result.phone
    return None


# ============================================================================
# CONFERENCE ROOM CRUD
# ============================================================================

@router.post("")
async def create_conference(
    conference: ConferenceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create a new conference room"""
    try:
        # Generate PINs if required but not provided
        host_pin = conference.host_pin
        participant_pin = conference.participant_pin

        if conference.pin_required:
            if not host_pin:
                host_pin = generate_pin()
            if not participant_pin:
                participant_pin = generate_pin()
                # Make sure host and participant PINs are different
                while participant_pin == host_pin:
                    participant_pin = generate_pin()

        result = db.execute(text("""
            INSERT INTO conference_rooms
            (room_name, friendly_name, max_participants, start_on_enter, end_on_exit,
             mute_on_entry, record_conference, pin_required, host_pin, participant_pin,
             status, created_by, is_active)
            VALUES
            (:room_name, :friendly_name, :max_participants, :start_on_enter, :end_on_exit,
             :mute_on_entry, :record, :pin_required, :host_pin, :participant_pin,
             'available', :created_by, TRUE)
            RETURNING id
        """), {
            "room_name": conference.room_name,
            "friendly_name": conference.friendly_name or conference.room_name,
            "max_participants": conference.max_participants,
            "start_on_enter": conference.start_on_enter,
            "end_on_exit": conference.end_on_exit,
            "mute_on_entry": conference.mute_on_entry,
            "record": conference.record_conference,
            "pin_required": conference.pin_required,
            "host_pin": host_pin,
            "participant_pin": participant_pin,
            "created_by": current_user.id if current_user else None
        })

        try:
            conf_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in create_conference: {e}")
            conf_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        db.commit()

        return {
            "success": True,
            "message": "Conference room created",
            "conference_id": conf_id,
            "room_name": conference.room_name,
            "host_pin": host_pin if conference.pin_required else None,
            "participant_pin": participant_pin if conference.pin_required else None
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_conferences(
    status: Optional[str] = None,  # available, in_progress, ended
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """List conference rooms"""
    try:
        conditions = []
        params = {}

        if not include_inactive:
            conditions.append("cr.is_active = TRUE")

        if status:
            conditions.append("cr.status = :status")
            params["status"] = status

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = """
            SELECT cr.id, cr.room_name, cr.friendly_name, cr.max_participants,
                   cr.status, cr.pin_required, cr.record_conference,
                   cr.started_at, cr.is_active, cr.created_at,
                   u.full_name as created_by_name,
                   COUNT(cp.id) as participant_count
            FROM conference_rooms cr
            LEFT JOIN users u ON u.id = cr.created_by
            LEFT JOIN conference_participants cp ON cp.conference_id = cr.id
                AND cp.status IN ('ringing', 'connected')
            """ + where_clause + """
            GROUP BY cr.id, u.full_name
            ORDER BY cr.created_at DESC
        """
        results = db.execute(text(query), params).fetchall()

        conferences = []
        for row in results:
            conferences.append({
                "id": row.id,
                "room_name": row.room_name,
                "friendly_name": row.friendly_name,
                "max_participants": row.max_participants,
                "status": row.status,
                "pin_required": row.pin_required,
                "record_conference": row.record_conference,
                "participant_count": row.participant_count,
                "started_at": safe_isoformat(row.started_at),
                "is_active": row.is_active,
                "created_by": row.created_by_name,
                "created_at": safe_isoformat(row.created_at)
            })

        return {
            "conferences": conferences,
            "count": len(conferences)
        }

    except Exception as e:
        logger.error(f"Error listing conferences: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{conference_id}")
async def get_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get conference details with participants"""
    try:
        conf = db.execute(text("""
            SELECT cr.*, u.full_name as created_by_name
            FROM conference_rooms cr
            LEFT JOIN users u ON u.id = cr.created_by
            WHERE cr.id = :id
        """), {"id": conference_id}).fetchone()

        if not conf:
            raise HTTPException(status_code=404, detail="Conference not found")

        # Get participants
        participants = db.execute(text("""
            SELECT cp.id, cp.call_sid, cp.phone_number, cp.name, cp.role,
                   cp.status, cp.is_muted, cp.is_on_hold, cp.joined_at,
                   cp.user_id, u.full_name as user_name
            FROM conference_participants cp
            LEFT JOIN users u ON u.id = cp.user_id
            WHERE cp.conference_id = :id
            ORDER BY cp.role, cp.joined_at
        """), {"id": conference_id}).fetchall()

        return {
            "id": conf.id,
            "room_name": conf.room_name,
            "friendly_name": conf.friendly_name,
            "max_participants": conf.max_participants,
            "start_on_enter": conf.start_on_enter,
            "end_on_exit": conf.end_on_exit,
            "mute_on_entry": conf.mute_on_entry,
            "record_conference": conf.record_conference,
            "pin_required": conf.pin_required,
            "host_pin": conf.host_pin if current_user else None,  # Only show to authenticated users
            "participant_pin": conf.participant_pin if current_user else None,
            "current_conference_sid": conf.current_conference_sid,
            "status": conf.status,
            "started_at": safe_isoformat(conf.started_at),
            "ended_at": safe_isoformat(conf.ended_at),
            "is_active": conf.is_active,
            "created_by": conf.created_by_name,
            "participants": [
                {
                    "id": p.id,
                    "call_sid": p.call_sid,
                    "phone": p.phone_number,
                    "name": p.name or p.user_name,
                    "user_id": p.user_id,
                    "role": p.role,
                    "status": p.status,
                    "is_muted": p.is_muted,
                    "is_on_hold": p.is_on_hold,
                    "joined_at": safe_isoformat(p.joined_at)
                }
                for p in participants
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{conference_id}")
async def update_conference(
    conference_id: int,
    conference: ConferenceUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Update conference settings"""
    try:
        existing = db.execute(text(
            "SELECT id FROM conference_rooms WHERE id = :id"
        ), {"id": conference_id}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Conference not found")

        updates = []
        params = {"conf_id": conference_id}

        field_mappings = {
            "friendly_name": "friendly_name",
            "max_participants": "max_participants",
            "start_on_enter": "start_on_enter",
            "end_on_exit": "end_on_exit",
            "mute_on_entry": "mute_on_entry",
            "record_conference": "record_conference",
            "pin_required": "pin_required",
            "host_pin": "host_pin",
            "participant_pin": "participant_pin",
            "is_active": "is_active"
        }

        for field, col in field_mappings.items():
            value = getattr(conference, field)
            if value is not None:
                updates.append(f"{col} = :{field}")
                params[field] = value

        updates.append("updated_at = CURRENT_TIMESTAMP")

        if updates:
            query = "UPDATE conference_rooms SET " + ", ".join(updates) + " WHERE id = :conf_id"
            db.execute(text(query), params)
            db.commit()

        return {"success": True, "message": "Conference updated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{conference_id}")
async def delete_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Deactivate a conference room"""
    try:
        result = db.execute(text("""
            UPDATE conference_rooms SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": conference_id})

        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conference not found")

        return {"success": True, "message": "Conference deactivated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CONFERENCE ACTIONS
# ============================================================================

@router.post("/{conference_id}/start")
async def start_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Start a conference (mark as in progress)"""
    try:
        conf = db.execute(text("""
            SELECT id, room_name, status FROM conference_rooms WHERE id = :id
        """), {"id": conference_id}).fetchone()

        if not conf:
            raise HTTPException(status_code=404, detail="Conference not found")

        if conf.status == "in_progress":
            return {"success": True, "message": "Conference already in progress"}

        db.execute(text("""
            UPDATE conference_rooms
            SET status = 'in_progress', started_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": conference_id})
        db.commit()

        return {
            "success": True,
            "message": "Conference started",
            "room_name": conf.room_name
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error starting conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{conference_id}/end")
async def end_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """End a conference and disconnect all participants"""
    try:
        provider = get_telephony_provider()
        if not provider:
            raise HTTPException(status_code=500, detail="Telephony not configured")

        conf = db.execute(text("""
            SELECT id, room_name, current_conference_sid FROM conference_rooms WHERE id = :id
        """), {"id": conference_id}).fetchone()

        if not conf:
            raise HTTPException(status_code=404, detail="Conference not found")

        # End the conference - disconnect all participants via their call SIDs
        if conf.current_conference_sid:
            try:
                # Get all connected participants and end their calls
                active_participants = db.execute(text("""
                    SELECT call_sid FROM conference_participants
                    WHERE conference_id = :id AND status IN ('ringing', 'connected') AND call_sid IS NOT NULL
                """), {"id": conference_id}).fetchall()
                for p in active_participants:
                    try:
                        provider.end_call(p.call_sid)
                    except Exception as e:
                        logger.warning(f"Error ending participant call {p.call_sid}: {e}")
            except Exception as telephony_error:
                logger.warning(f"Error ending conference: {telephony_error}")

        # Update all participants
        db.execute(text("""
            UPDATE conference_participants
            SET status = 'left', left_at = CURRENT_TIMESTAMP
            WHERE conference_id = :id AND status IN ('ringing', 'connected')
        """), {"id": conference_id})

        # Update conference
        db.execute(text("""
            UPDATE conference_rooms
            SET status = 'ended', ended_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": conference_id})

        db.commit()

        return {"success": True, "message": "Conference ended"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error ending conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# PARTICIPANT MANAGEMENT
# ============================================================================

@router.post("/{conference_id}/participants")
async def add_participant(
    conference_id: int,
    request: AddParticipantRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Dial out to add a participant to conference"""
    try:
        provider = get_telephony_provider()
        if not provider:
            raise HTTPException(status_code=500, detail="Telephony not configured")

        conf = db.execute(text("""
            SELECT id, room_name, max_participants, current_conference_sid, mute_on_entry
            FROM conference_rooms WHERE id = :id AND is_active = TRUE
        """), {"id": conference_id}).fetchone()

        if not conf:
            raise HTTPException(status_code=404, detail="Conference not found")

        # Check participant limit
        current_count = db.execute(text("""
            SELECT COUNT(*) as count FROM conference_participants
            WHERE conference_id = :id AND status IN ('ringing', 'connected')
        """), {"id": conference_id}).fetchone()

        if current_count.count >= conf.max_participants:
            raise HTTPException(status_code=400, detail="Conference is at capacity")

        # Determine phone number
        phone = None
        user_id = None
        name = request.announce_name

        if request.phone:
            phone = format_phone(request.phone)
        elif request.user_id:
            user_id = request.user_id
            phone = get_user_phone(db, request.user_id)
            if not phone:
                raise HTTPException(status_code=400, detail="User has no phone configured")
            phone = format_phone(phone)

            if not name:
                user = db.execute(text("SELECT COALESCE(es.full_name, u.email) AS name FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id WHERE u.id = :id"), {"id": user_id}).fetchone()
                if user:
                    name = user.name
        else:
            raise HTTPException(status_code=400, detail="Must provide phone or user_id")

        # Create participant record
        result = db.execute(text("""
            INSERT INTO conference_participants
            (conference_id, user_id, phone_number, name, role, status, is_muted)
            VALUES
            (:conf_id, :user_id, :phone, :name, :role, 'ringing', :muted)
            RETURNING id
        """), {
            "conf_id": conference_id,
            "user_id": user_id,
            "phone": phone,
            "name": name,
            "role": request.role.value,
            "muted": request.muted or conf.mute_on_entry
        })

        try:
            participant_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in add_participant: {e}")
            participant_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        # Dial out to add participant
        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        join_url = f"{base_url}/api/v1/conferences/twiml/join?conf_id={conference_id}&participant_id={participant_id}&role={request.role.value}"

        try:
            call_result = provider.place_call(
                to=phone,
                from_=os.getenv("TELNYX_PHONE_NUMBER", ""),
                url=join_url,
                status_callback=f"{base_url}/api/v1/conferences/webhook/participant-status?participant_id={participant_id}",
            )

            call_sid = call_result.call_sid if hasattr(call_result, 'call_sid') else str(call_result)

            # Update with call SID
            db.execute(text("""
                UPDATE conference_participants SET call_sid = :call_sid WHERE id = :id
            """), {"call_sid": call_sid, "id": participant_id})

            db.commit()

            return {
                "success": True,
                "message": f"Calling {name or phone}",
                "participant_id": participant_id,
                "call_sid": call_sid
            }

        except Exception as telephony_error:
            logger.error(f"Telephony error adding participant: {telephony_error}")
            db.execute(text("""
                UPDATE conference_participants SET status = 'failed' WHERE id = :id
            """), {"id": participant_id})
            db.commit()
            raise HTTPException(status_code=500, detail=str(telephony_error))

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error adding participant: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{conference_id}/participants/{participant_id}/action")
async def participant_action(
    conference_id: int,
    participant_id: int,
    action: ParticipantAction,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Perform action on a participant (mute, unmute, hold, remove)"""
    try:
        provider = get_telephony_provider()
        if not provider:
            raise HTTPException(status_code=500, detail="Telephony not configured")

        # Get participant and conference
        participant = db.execute(text("""
            SELECT cp.id, cp.call_sid, cp.status, cr.current_conference_sid
            FROM conference_participants cp
            JOIN conference_rooms cr ON cr.id = cp.conference_id
            WHERE cp.id = :participant_id AND cp.conference_id = :conf_id
        """), {"participant_id": participant_id, "conf_id": conference_id}).fetchone()

        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found")

        if participant.status != "connected":
            raise HTTPException(status_code=400, detail="Participant not connected")

        call_sid = participant.call_sid

        if not call_sid:
            raise HTTPException(status_code=400, detail="Cannot modify participant - no active call")

        try:
            if action.action == "mute":
                if hasattr(provider, 'mute_participant'):
                    provider.mute_participant(call_sid, muted=True)
                db.execute(text("""
                    UPDATE conference_participants SET is_muted = TRUE WHERE id = :id
                """), {"id": participant_id})

            elif action.action == "unmute":
                if hasattr(provider, 'mute_participant'):
                    provider.mute_participant(call_sid, muted=False)
                db.execute(text("""
                    UPDATE conference_participants SET is_muted = FALSE WHERE id = :id
                """), {"id": participant_id})

            elif action.action == "hold":
                if hasattr(provider, 'hold_participant'):
                    provider.hold_participant(call_sid, hold=True)
                db.execute(text("""
                    UPDATE conference_participants SET is_on_hold = TRUE WHERE id = :id
                """), {"id": participant_id})

            elif action.action == "unhold":
                if hasattr(provider, 'hold_participant'):
                    provider.hold_participant(call_sid, hold=False)
                db.execute(text("""
                    UPDATE conference_participants SET is_on_hold = FALSE WHERE id = :id
                """), {"id": participant_id})

            elif action.action == "remove":
                provider.end_call(call_sid)
                db.execute(text("""
                    UPDATE conference_participants
                    SET status = 'left', left_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), {"id": participant_id})

            else:
                raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

            db.commit()
            return {"success": True, "message": f"Participant {action.action}d"}

        except Exception as telephony_error:
            logger.error(f"Telephony error on participant action: {telephony_error}")
            raise HTTPException(status_code=500, detail=str(telephony_error))

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error on participant action: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{conference_id}/mute-all")
async def mute_all_participants(
    conference_id: int,
    except_hosts: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Mute all participants (optionally except hosts)"""
    try:
        provider = get_telephony_provider()
        if not provider:
            raise HTTPException(status_code=500, detail="Telephony not configured")

        conf = db.execute(text("""
            SELECT current_conference_sid FROM conference_rooms WHERE id = :id
        """), {"id": conference_id}).fetchone()

        if not conf or not conf.current_conference_sid:
            raise HTTPException(status_code=400, detail="Conference not active")

        # Get participants to mute
        role_filter = "AND role NOT IN ('host', 'moderator')" if except_hosts else ""
        query = """
            SELECT id, call_sid FROM conference_participants
            WHERE conference_id = :id AND status = 'connected' """ + role_filter + """
        """
        participants = db.execute(text(query), {"id": conference_id}).fetchall()

        muted_count = 0
        for p in participants:
            try:
                if hasattr(provider, 'mute_participant'):
                    provider.mute_participant(p.call_sid, muted=True)
                db.execute(text("UPDATE conference_participants SET is_muted = TRUE WHERE id = :id"), {"id": p.id})
                muted_count += 1
            except Exception as e:
                logger.warning(f"Could not mute participant {p.id}: {e}")

        db.commit()

        return {"success": True, "message": f"Muted {muted_count} participants"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error muting all: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TWIML ENDPOINTS
# ============================================================================

@router.post("/twiml/join")
@router.get("/twiml/join")
async def join_conference_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML for joining a conference.
    Used when dialing out to add participants.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        form_data = await request.form() if request.method == "POST" else {}

        conf_id = query_params.get("conf_id")
        participant_id = query_params.get("participant_id")
        role = query_params.get("role", "participant")

        # Get conference settings
        conf = db.execute(text("""
            SELECT room_name, start_on_enter, end_on_exit, mute_on_entry, record_conference
            FROM conference_rooms WHERE id = :id
        """), {"id": conf_id}).fetchone()

        if not conf:
            response = TeXMLResponse()
            response.say("Conference not found.", voice="Polly.Joanna")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")

        # Get participant settings
        is_host = role in ["host", "moderator"]
        muted = conf.mute_on_entry and not is_host

        if participant_id:
            part = db.execute(text("""
                SELECT is_muted FROM conference_participants WHERE id = :id
            """), {"id": participant_id}).fetchone()
            if part:
                muted = part.is_muted

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        response = TeXMLResponse()
        response.say("Joining the conference.", voice="Polly.Joanna")

        dial = response.dial()
        dial.conference(
            conf.room_name,
            start_conference_on_enter=conf.start_on_enter if is_host else False,
            end_conference_on_exit=conf.end_on_exit if is_host else False,
            muted=muted,
            record=conf.record_conference,
            beep=True,
            status_callback=f"{base_url}/api/v1/conferences/webhook/conference-status?conf_id={conf_id}",
            status_callback_event="start end join leave mute hold"
        )

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in join TwiML: {e}")
        response = TeXMLResponse()
        response.say("Error joining conference.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/dial-in")
@router.get("/twiml/dial-in")
async def dial_in_conference_twiml(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    TwiML for inbound callers to dial into a conference.
    Handles PIN verification if required.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        form_data = await request.form() if request.method == "POST" else {}

        room_name = query_params.get("room")
        digits = form_data.get("Digits", "")
        attempt = int(query_params.get("attempt", "1"))

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        # If room name provided, look it up
        if room_name:
            conf = db.execute(text("""
                SELECT id, room_name, pin_required, host_pin, participant_pin
                FROM conference_rooms
                WHERE room_name = :name AND is_active = TRUE
            """), {"name": room_name}).fetchone()
        else:
            # Use default or prompt for room
            conf = db.execute(text("""
                SELECT id, room_name, pin_required, host_pin, participant_pin
                FROM conference_rooms
                WHERE is_active = TRUE AND status = 'in_progress'
                ORDER BY started_at DESC LIMIT 1
            """)).fetchone()

        if not conf:
            response = TeXMLResponse()
            response.say("No active conference found. Goodbye.", voice="Polly.Joanna")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")

        response = TeXMLResponse()

        # Handle PIN if required
        if conf.pin_required:
            if digits:
                # Verify PIN
                if digits == conf.host_pin:
                    # Host joining
                    response.say("Welcome, host.", voice="Polly.Joanna")
                    response.redirect(f"{base_url}/api/v1/conferences/twiml/join?conf_id={conf.id}&role=host")
                    return Response(content=str(response), media_type="application/xml")

                elif digits == conf.participant_pin:
                    # Participant joining
                    response.say("Welcome.", voice="Polly.Joanna")
                    response.redirect(f"{base_url}/api/v1/conferences/twiml/join?conf_id={conf.id}&role=participant")
                    return Response(content=str(response), media_type="application/xml")

                else:
                    # Wrong PIN
                    if attempt < 3:
                        response.say("Invalid PIN. Please try again.", voice="Polly.Joanna")
                        gather = response.gather(
                            num_digits=6,
                            action=f"{base_url}/api/v1/conferences/twiml/dial-in?room={room_name}&attempt={attempt + 1}",
                            timeout=10
                        )
                        gather.say("Enter your conference PIN.", voice="Polly.Joanna")
                    else:
                        response.say("Too many incorrect attempts. Goodbye.", voice="Polly.Joanna")
                        response.hangup()
                    return Response(content=str(response), media_type="application/xml")

            else:
                # Prompt for PIN
                gather = response.gather(
                    num_digits=6,
                    action=f"{base_url}/api/v1/conferences/twiml/dial-in?room={room_name}",
                    timeout=10
                )
                gather.say("Please enter your conference PIN.", voice="Polly.Joanna")

                response.say("No PIN entered.", voice="Polly.Joanna")
                response.redirect(f"{base_url}/api/v1/conferences/twiml/dial-in?room={room_name}&attempt=2")

        else:
            # No PIN required - join as participant
            response.redirect(f"{base_url}/api/v1/conferences/twiml/join?conf_id={conf.id}&role=participant")

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in dial-in TwiML: {e}")
        response = TeXMLResponse()
        response.say("Error connecting to conference.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


# ============================================================================
# WEBHOOKS
# ============================================================================

@router.post("/webhook/participant-status")
async def participant_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(require_telnyx_webhook)
):
    """Webhook for participant call status updates"""

    try:
        query_params = request.query_params
        form_data = await request.form()

        participant_id = query_params.get("participant_id")
        call_status = form_data.get("CallStatus", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Participant {participant_id} status: {call_status}")

        if call_status == "answered":
            db.execute(text("""
                UPDATE conference_participants
                SET status = 'connected', joined_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": participant_id})

        elif call_status == "completed":
            db.execute(text("""
                UPDATE conference_participants
                SET status = 'left', left_at = CURRENT_TIMESTAMP,
                    duration_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - joined_at))
                WHERE id = :id
            """), {"id": participant_id})

        elif call_status in ["busy", "no-answer", "failed", "canceled"]:
            db.execute(text("""
                UPDATE conference_participants SET status = 'failed' WHERE id = :id
            """), {"id": participant_id})

        db.commit()
        return {"status": "ok"}

    except SQLAlchemyError as e:
        logger.error(f"Error in participant status webhook: {e}")
        return {"status": "error"}


@router.post("/webhook/conference-status")
async def conference_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(require_telnyx_webhook)
):
    """Webhook for conference status updates"""

    try:
        query_params = request.query_params
        form_data = await request.form()

        conf_id = query_params.get("conf_id")
        status_event = form_data.get("StatusCallbackEvent", "")
        conference_sid = form_data.get("ConferenceSid", "")
        call_sid = form_data.get("CallSid", "")
        muted = form_data.get("Muted", "false") == "true"
        hold = form_data.get("Hold", "false") == "true"

        logger.info(f"Conference {conf_id} event: {status_event}")

        if status_event == "conference-start":
            db.execute(text("""
                UPDATE conference_rooms
                SET status = 'in_progress', current_conference_sid = :sid,
                    started_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": conf_id, "sid": conference_sid})

        elif status_event == "conference-end":
            db.execute(text("""
                UPDATE conference_rooms
                SET status = 'ended', ended_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": conf_id})

        elif status_event == "participant-join":
            # Update participant status
            db.execute(text("""
                UPDATE conference_participants
                SET status = 'connected', joined_at = CURRENT_TIMESTAMP
                WHERE conference_id = :conf_id AND call_sid = :call_sid
            """), {"conf_id": conf_id, "call_sid": call_sid})

        elif status_event == "participant-leave":
            db.execute(text("""
                UPDATE conference_participants
                SET status = 'left', left_at = CURRENT_TIMESTAMP
                WHERE conference_id = :conf_id AND call_sid = :call_sid
            """), {"conf_id": conf_id, "call_sid": call_sid})

        elif status_event == "participant-mute":
            db.execute(text("""
                UPDATE conference_participants SET is_muted = :muted
                WHERE conference_id = :conf_id AND call_sid = :call_sid
            """), {"conf_id": conf_id, "call_sid": call_sid, "muted": muted})

        elif status_event == "participant-hold":
            db.execute(text("""
                UPDATE conference_participants SET is_on_hold = :hold
                WHERE conference_id = :conf_id AND call_sid = :call_sid
            """), {"conf_id": conf_id, "call_sid": call_sid, "hold": hold})

        db.commit()
        return {"status": "ok"}

    except SQLAlchemyError as e:
        logger.error(f"Error in conference status webhook: {e}")
        return {"status": "error"}


# ============================================================================
# QUICK CONFERENCE
# ============================================================================

@router.post("/quick")
async def create_quick_conference(
    participants: List[str],  # List of phone numbers or user IDs
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Create a quick ad-hoc conference and dial all participants.
    Useful for instant multi-party calls.
    """
    try:
        import uuid

        # Create conference room
        room_name = f"quick-conf-{uuid.uuid4().hex[:8]}"

        result = db.execute(text("""
            INSERT INTO conference_rooms
            (room_name, friendly_name, max_participants, start_on_enter,
             status, created_by, is_active)
            VALUES
            (:room_name, :friendly_name, :max, TRUE, 'in_progress', :created_by, TRUE)
            RETURNING id
        """), {
            "room_name": room_name,
            "friendly_name": f"Quick Conference",
            "max": len(participants) + 5,
            "created_by": current_user.id if current_user else None
        })

        try:
            conf_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in quick_conference: {e}")
            conf_id = result.lastrowid or db.execute(text("SELECT last_insert_rowid()")).scalar()

        db.commit()

        # Add all participants
        added = []
        for p in participants:
            try:
                if p.isdigit() or (p.startswith("+") and p[1:].isdigit()):
                    # Phone number
                    req = AddParticipantRequest(phone=p)
                else:
                    # User ID
                    req = AddParticipantRequest(user_id=int(p))

                result = await add_participant(conf_id, req, db, current_user)
                added.append(result)
            except SQLAlchemyError as e:
                logger.warning(f"Could not add participant {p}: {e}")
                added.append({"success": False, "participant": p, "error": "Internal server error"})

        return {
            "success": True,
            "message": "Quick conference created",
            "conference_id": conf_id,
            "room_name": room_name,
            "participants_added": added
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating quick conference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
