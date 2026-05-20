"""
Call Queue Routes
Implements call queuing with wait time estimation and position announcements
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging
import json
import os
import asyncio

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from middleware.webhook_verification import require_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/queues", tags=["call-queues"])


def safe_isoformat(dt_value) -> Optional[str]:
    """Safely convert datetime to ISO format string, handling both datetime objects and strings"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        return dt_value  # Already a string (SQLite returns strings)
    if hasattr(dt_value, 'isoformat'):
        return dt_value.isoformat()
    return str(dt_value)


def parse_datetime(dt_value) -> Optional[datetime]:
    """Parse a datetime value that might be a string or datetime object"""
    if dt_value is None:
        return None
    if isinstance(dt_value, datetime):
        return dt_value
    if isinstance(dt_value, str):
        try:
            # Try ISO format first
            return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
        except ValueError:
            try:
                # Try common database format
                return datetime.strptime(dt_value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return None
    return None


def calc_wait_time(entered_at) -> float:
    """Calculate wait time in seconds from entered_at to now"""
    dt = parse_datetime(entered_at)
    if dt is None:
        return 0
    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
    return (now - dt).total_seconds()


from auth.dependencies import get_current_user_flexible  # dedup
def get_telephony_provider():
    """Get telephony provider"""
    from telephony.provider import get_telephony_provider as _get_provider
    return _get_provider()


# ============================================================================
# MODELS
# ============================================================================

class QueueCreate(BaseModel):
    """Create call queue"""
    name: str
    friendly_name: Optional[str] = None
    description: Optional[str] = None
    max_wait_time_seconds: int = 600  # 10 minutes
    max_queue_size: int = 20
    announce_position: bool = True
    announce_wait_time: bool = True
    position_announcement_interval: int = 60  # seconds
    hold_music_id: Optional[int] = None
    hold_music_url: Optional[str] = None
    comfort_message: Optional[str] = None
    comfort_message_interval: int = 30  # seconds
    overflow_action: str = "voicemail"  # voicemail, transfer, hangup
    overflow_target: Optional[str] = None


class QueueUpdate(BaseModel):
    """Update call queue"""
    friendly_name: Optional[str] = None
    description: Optional[str] = None
    max_wait_time_seconds: Optional[int] = None
    max_queue_size: Optional[int] = None
    announce_position: Optional[bool] = None
    announce_wait_time: Optional[bool] = None
    position_announcement_interval: Optional[int] = None
    hold_music_id: Optional[int] = None
    hold_music_url: Optional[str] = None
    comfort_message: Optional[str] = None
    comfort_message_interval: Optional[int] = None
    overflow_action: Optional[str] = None
    overflow_target: Optional[str] = None
    is_active: Optional[bool] = None


class QueueMemberAdd(BaseModel):
    """Add member to queue"""
    user_id: int
    priority: int = 0  # Higher = more priority
    wrap_up_time: int = 30  # seconds after call before next


class QueueStats(BaseModel):
    """Queue statistics"""
    queue_id: int
    queue_name: str
    current_size: int
    avg_wait_time: float
    longest_wait: int
    calls_waiting: int
    agents_available: int
    agents_on_call: int


# ============================================================================
# QUEUE CRUD ENDPOINTS
# ============================================================================

@router.post("")
async def create_queue(
    queue: QueueCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create a new call queue"""
    try:
        # Get hold music URL if ID provided
        hold_music_url = queue.hold_music_url
        if queue.hold_music_id and not hold_music_url:
            result = await db.execute(text("""
                SELECT audio_url FROM hold_music WHERE id = :id AND is_active = TRUE
            """), {"id": queue.hold_music_id}).fetchone()
            if result:
                hold_music_url = result.audio_url

        result = await db.execute(text("""
            INSERT INTO call_queues
            (name, friendly_name, description, max_wait_time_seconds, max_queue_size,
             announce_position, announce_wait_time, position_announcement_interval,
             hold_music_id, hold_music_url, comfort_message, comfort_message_interval,
             overflow_action, overflow_target, is_active)
            VALUES
            (:name, :friendly_name, :description, :max_wait, :max_size,
             :announce_pos, :announce_wait, :pos_interval,
             :music_id, :music_url, :comfort_msg, :comfort_interval,
             :overflow_action, :overflow_target, TRUE)
            RETURNING id
        """), {
            "name": queue.name,
            "friendly_name": queue.friendly_name or queue.name.title(),
            "description": queue.description,
            "max_wait": queue.max_wait_time_seconds,
            "max_size": queue.max_queue_size,
            "announce_pos": queue.announce_position,
            "announce_wait": queue.announce_wait_time,
            "pos_interval": queue.position_announcement_interval,
            "music_id": queue.hold_music_id,
            "music_url": hold_music_url,
            "comfort_msg": queue.comfort_message,
            "comfort_interval": queue.comfort_message_interval,
            "overflow_action": queue.overflow_action,
            "overflow_target": queue.overflow_target
        })

        try:
            queue_id = result.fetchone()[0]
        except Exception as e:
            logger.warning(f"Error fetching queue_id from RETURNING clause: {e}")
            queue_id = result.lastrowid or await db.execute(text("SELECT last_insert_rowid()")).scalar()

        # Create telephony queue (if provider supports it)
        try:
            provider = get_telephony_provider()
            if provider and hasattr(provider, 'create_queue'):
                queue_result = provider.create_queue(friendly_name=queue.name, max_size=queue.max_queue_size)
                if queue_result:
                    queue_sid = queue_result.sid if hasattr(queue_result, 'sid') else str(queue_result)
                    await db.execute(text("""
                        UPDATE call_queues SET telephony_queue_sid = :sid WHERE id = :id
                    """), {"sid": queue_sid, "id": queue_id})
        except Exception as telephony_error:
            logger.warning(f"Could not create telephony queue: {telephony_error}")

        await db.commit()

        return {
            "success": True,
            "message": "Queue created",
            "queue_id": queue_id
        }

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_queues(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """List all call queues with current status"""
    try:
        where_clause = "" if include_inactive else "WHERE q.is_active = TRUE"

        query = """
            SELECT q.id, q.name, q.friendly_name, q.description,
                   q.max_wait_time_seconds, q.max_queue_size,
                   q.is_active, q.telephony_queue_sid, q.created_at,
                   COUNT(DISTINCT qm.id) as member_count,
                   COUNT(DISTINCT CASE WHEN qe.status = 'waiting' THEN qe.id END) as waiting_calls
            FROM call_queues q
            LEFT JOIN queue_members qm ON qm.queue_id = q.id AND qm.is_active = TRUE
            LEFT JOIN queue_entries qe ON qe.queue_id = q.id AND qe.status = 'waiting'
            """ + where_clause + """
            GROUP BY q.id
            ORDER BY q.name
        """
        results = await db.execute(text(query)).fetchall()

        queues = []
        for row in results:
            queues.append({
                "id": row.id,
                "name": row.name,
                "friendly_name": row.friendly_name,
                "description": row.description,
                "max_wait_time_seconds": row.max_wait_time_seconds,
                "max_queue_size": row.max_queue_size,
                "is_active": row.is_active,
                "telephony_queue_sid": row.telephony_queue_sid,
                "member_count": row.member_count,
                "waiting_calls": row.waiting_calls,
                "created_at": safe_isoformat(row.created_at)
            })

        return {
            "queues": queues,
            "count": len(queues)
        }

    except Exception as e:
        logger.error(f"Error listing queues: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{queue_id}")
async def get_queue(
    queue_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get queue details with members and current entries"""
    try:
        queue = await db.execute(text("""
            SELECT * FROM call_queues WHERE id = :queue_id
        """), {"queue_id": queue_id}).fetchone()

        if not queue:
            raise HTTPException(status_code=404, detail="Queue not found")

        # Get members
        members = await db.execute(text("""
            SELECT qm.id, qm.user_id, qm.priority, qm.wrap_up_time, qm.is_active,
                   COALESCE(es.full_name, u.email) as user_name
            FROM queue_members qm
            JOIN users u ON u.id = qm.user_id
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE qm.queue_id = :queue_id
            ORDER BY qm.priority DESC, COALESCE(es.full_name, u.email)
        """), {"queue_id": queue_id}).fetchall()

        # Get waiting entries
        entries = await db.execute(text("""
            SELECT id, call_sid, caller_phone, caller_name, position,
                   entered_at, estimated_wait_seconds, status
            FROM queue_entries
            WHERE queue_id = :queue_id AND status = 'waiting'
            ORDER BY position
        """), {"queue_id": queue_id}).fetchall()

        return {
            "id": queue.id,
            "name": queue.name,
            "friendly_name": queue.friendly_name,
            "description": queue.description,
            "max_wait_time_seconds": queue.max_wait_time_seconds,
            "max_queue_size": queue.max_queue_size,
            "announce_position": queue.announce_position,
            "announce_wait_time": queue.announce_wait_time,
            "position_announcement_interval": queue.position_announcement_interval,
            "hold_music_id": queue.hold_music_id,
            "hold_music_url": queue.hold_music_url,
            "comfort_message": queue.comfort_message,
            "comfort_message_interval": queue.comfort_message_interval,
            "overflow_action": queue.overflow_action,
            "overflow_target": queue.overflow_target,
            "is_active": queue.is_active,
            "telephony_queue_sid": queue.telephony_queue_sid,
            "members": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "user_name": m.user_name,
                    "user_phone": m.user_phone,
                    "priority": m.priority,
                    "wrap_up_time": m.wrap_up_time,
                    "is_active": m.is_active
                }
                for m in members
            ],
            "waiting_entries": [
                {
                    "id": e.id,
                    "call_sid": e.call_sid,
                    "caller_phone": e.caller_phone,
                    "caller_name": e.caller_name,
                    "position": e.position,
                    "entered_at": safe_isoformat(e.entered_at),
                    "estimated_wait_seconds": e.estimated_wait_seconds,
                    "wait_time_so_far": calc_wait_time(e.entered_at)
                }
                for e in entries
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{queue_id}")
async def update_queue(
    queue_id: int,
    queue: QueueUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Update queue settings"""
    try:
        existing = await db.execute(text(
            "SELECT id FROM call_queues WHERE id = :queue_id"
        ), {"queue_id": queue_id}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Queue not found")

        updates = []
        params = {"queue_id": queue_id}

        field_mappings = {
            "friendly_name": "friendly_name",
            "description": "description",
            "max_wait_time_seconds": "max_wait_time_seconds",
            "max_queue_size": "max_queue_size",
            "announce_position": "announce_position",
            "announce_wait_time": "announce_wait_time",
            "position_announcement_interval": "position_announcement_interval",
            "hold_music_id": "hold_music_id",
            "hold_music_url": "hold_music_url",
            "comfort_message": "comfort_message",
            "comfort_message_interval": "comfort_message_interval",
            "overflow_action": "overflow_action",
            "overflow_target": "overflow_target",
            "is_active": "is_active"
        }

        for field, col in field_mappings.items():
            value = getattr(queue, field)
            if value is not None:
                updates.append(f"{col} = :{field}")
                params[field] = value

        updates.append("updated_at = CURRENT_TIMESTAMP")

        if updates:
            query = "UPDATE call_queues SET " + ", ".join(updates) + " WHERE id = :queue_id"
            await db.execute(text(query), params)
            await db.commit()

        return {"success": True, "message": "Queue updated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error updating queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{queue_id}")
async def delete_queue(
    queue_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Deactivate a queue"""
    try:
        result = await db.execute(text("""
            UPDATE call_queues SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :queue_id
        """), {"queue_id": queue_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Queue not found")

        return {"success": True, "message": "Queue deactivated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error deleting queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# QUEUE MEMBER MANAGEMENT
# ============================================================================

@router.post("/{queue_id}/members")
async def add_queue_member(
    queue_id: int,
    member: QueueMemberAdd,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Add a user to a queue"""
    try:
        # Verify queue exists
        queue = await db.execute(text(
            "SELECT id FROM call_queues WHERE id = :queue_id"
        ), {"queue_id": queue_id}).fetchone()

        if not queue:
            raise HTTPException(status_code=404, detail="Queue not found")

        # Check if already a member
        existing = await db.execute(text("""
            SELECT id FROM queue_members
            WHERE queue_id = :queue_id AND user_id = :user_id
        """), {"queue_id": queue_id, "user_id": member.user_id}).fetchone()

        if existing:
            # Reactivate if inactive
            await db.execute(text("""
                UPDATE queue_members
                SET is_active = TRUE, priority = :priority, wrap_up_time = :wrap_up
                WHERE id = :id
            """), {"id": existing.id, "priority": member.priority, "wrap_up": member.wrap_up_time})
            await db.commit()
            return {"success": True, "message": "Member reactivated", "member_id": existing.id}

        result = await db.execute(text("""
            INSERT INTO queue_members (queue_id, user_id, priority, wrap_up_time, is_active)
            VALUES (:queue_id, :user_id, :priority, :wrap_up, TRUE)
            RETURNING id
        """), {
            "queue_id": queue_id,
            "user_id": member.user_id,
            "priority": member.priority,
            "wrap_up": member.wrap_up_time
        })

        try:
            member_id = result.fetchone()[0]
        except Exception as e:
            logger.warning(f"Error fetching member_id from RETURNING clause: {e}")
            member_id = result.lastrowid or await db.execute(text("SELECT last_insert_rowid()")).scalar()

        await db.commit()

        return {"success": True, "message": "Member added", "member_id": member_id}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error adding queue member: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{queue_id}/members/{user_id}")
async def remove_queue_member(
    queue_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """Remove a user from a queue"""
    try:
        result = await db.execute(text("""
            UPDATE queue_members SET is_active = FALSE
            WHERE queue_id = :queue_id AND user_id = :user_id
        """), {"queue_id": queue_id, "user_id": user_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Member not found")

        return {"success": True, "message": "Member removed"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error removing queue member: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# WAIT TIME ESTIMATION
# ============================================================================

def estimate_wait_time(db: Session, queue_id: int) -> int:
    """
    Estimate wait time based on:
    1. Current position in queue
    2. Historical average handle time
    3. Number of available agents
    """
    try:
        # Get queue settings
        queue = db.execute(text("""
            SELECT max_wait_time_seconds FROM call_queues WHERE id = :id
        """), {"id": queue_id}).fetchone()

        # Get current queue size
        waiting = db.execute(text("""
            SELECT COUNT(*) as count FROM queue_entries
            WHERE queue_id = :id AND status = 'waiting'
        """), {"id": queue_id}).fetchone()
        queue_size = waiting.count if waiting else 0

        # Get active member count
        members = db.execute(text("""
            SELECT COUNT(*) as count FROM queue_members
            WHERE queue_id = :id AND is_active = TRUE
        """), {"id": queue_id}).fetchone()
        agent_count = members.count if members else 1

        # Get average handle time from recent calls (last 50)
        avg_handle = db.execute(text("""
            SELECT AVG(actual_wait_seconds) as avg_wait
            FROM queue_entries
            WHERE queue_id = :id
              AND status = 'connected'
              AND actual_wait_seconds IS NOT NULL
            ORDER BY connected_at DESC
            LIMIT 50
        """), {"id": queue_id}).fetchone()

        avg_handle_time = avg_handle.avg_wait if avg_handle and avg_handle.avg_wait else 120  # Default 2 min

        # Calculate estimated wait
        if agent_count > 0:
            estimated = (queue_size / agent_count) * avg_handle_time
        else:
            estimated = queue_size * avg_handle_time

        # Cap at max wait time
        if queue and queue.max_wait_time_seconds:
            estimated = min(estimated, queue.max_wait_time_seconds)

        return int(estimated)

    except Exception as e:
        logger.error(f"Error estimating wait time: {e}")
        return 120  # Default 2 minutes


@router.get("/stats")
async def get_all_queue_stats(
    db: AsyncSession = Depends(get_async_db)
):
    """Get aggregate statistics across all active queues (CQ-002)"""
    try:
        # Per-queue stats
        queues = await db.execute(text("""
            SELECT q.id, q.name, q.friendly_name,
                   COUNT(DISTINCT CASE WHEN qe.status = 'waiting' THEN qe.id END) as calls_waiting,
                   COUNT(DISTINCT CASE WHEN qm.is_active = TRUE THEN qm.id END) as agents_available
            FROM call_queues q
            LEFT JOIN queue_entries qe ON qe.queue_id = q.id AND qe.status = 'waiting'
            LEFT JOIN queue_members qm ON qm.queue_id = q.id AND qm.is_active = TRUE
            WHERE q.is_active = TRUE
            GROUP BY q.id, q.name, q.friendly_name
            ORDER BY q.name
        """)).fetchall()

        # Aggregate stats
        agg = await db.execute(text("""
            SELECT
                COUNT(DISTINCT q.id) as total_queues,
                COUNT(DISTINCT CASE WHEN qe.status = 'waiting' THEN qe.id END) as total_waiting,
                COUNT(DISTINCT CASE WHEN qm.is_active = TRUE THEN qm.id END) as total_agents
            FROM call_queues q
            LEFT JOIN queue_entries qe ON qe.queue_id = q.id AND qe.status = 'waiting'
            LEFT JOIN queue_members qm ON qm.queue_id = q.id AND qm.is_active = TRUE
            WHERE q.is_active = TRUE
        """)).fetchone()

        # Today's aggregate
        today = await db.execute(text("""
            SELECT
                COUNT(*) as calls_today,
                AVG(actual_wait_seconds) as avg_wait_today,
                MAX(actual_wait_seconds) as max_wait_today,
                COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned_today,
                COUNT(CASE WHEN status = 'connected' THEN 1 END) as connected_today
            FROM queue_entries
            WHERE entered_at >= CURRENT_DATE
        """)).fetchone()

        queue_list = []
        for q in queues:
            queue_list.append({
                "queue_id": q.id,
                "queue_name": q.name,
                "friendly_name": q.friendly_name,
                "calls_waiting": q.calls_waiting or 0,
                "agents_available": q.agents_available or 0,
            })

        return {
            "summary": {
                "total_queues": agg.total_queues or 0,
                "total_calls_waiting": agg.total_waiting or 0,
                "total_agents_available": agg.total_agents or 0,
            },
            "today": {
                "total_calls": today.calls_today or 0,
                "connected": today.connected_today or 0,
                "abandoned": today.abandoned_today or 0,
                "avg_wait_seconds": int(today.avg_wait_today or 0),
                "max_wait_seconds": int(today.max_wait_today or 0),
                "abandonment_rate": round(
                    (today.abandoned_today or 0) / max(today.calls_today or 1, 1) * 100, 1
                ),
            },
            "queues": queue_list,
        }

    except Exception as e:
        logger.error(f"Error getting aggregate queue stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{queue_id}/stats")
async def get_queue_stats(
    queue_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get real-time queue statistics"""
    try:
        queue = await db.execute(text("""
            SELECT id, name, friendly_name FROM call_queues WHERE id = :id
        """), {"id": queue_id}).fetchone()

        if not queue:
            raise HTTPException(status_code=404, detail="Queue not found")

        # Current queue stats
        entries = await db.execute(text("""
            SELECT
                COUNT(*) as total_waiting,
                MIN(entered_at) as oldest_entry,
                AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - entered_at))) as avg_wait
            FROM queue_entries
            WHERE queue_id = :id AND status = 'waiting'
        """), {"id": queue_id}).fetchone()

        # Agent stats
        agents = await db.execute(text("""
            SELECT
                COUNT(*) as total_agents,
                COUNT(CASE WHEN qm.is_active THEN 1 END) as available_agents
            FROM queue_members qm
            WHERE qm.queue_id = :id
        """), {"id": queue_id}).fetchone()

        # Today's stats
        today_stats = await db.execute(text("""
            SELECT
                COUNT(*) as calls_today,
                AVG(actual_wait_seconds) as avg_wait_today,
                MAX(actual_wait_seconds) as max_wait_today,
                COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned_today
            FROM queue_entries
            WHERE queue_id = :id
              AND entered_at >= CURRENT_DATE
        """), {"id": queue_id}).fetchone()

        longest_wait = 0
        if entries.oldest_entry:
            longest_wait = int((datetime.now(timezone.utc) - entries.oldest_entry.replace(tzinfo=timezone.utc)).total_seconds())

        return {
            "queue_id": queue.id,
            "queue_name": queue.name,
            "friendly_name": queue.friendly_name,
            "current": {
                "calls_waiting": entries.total_waiting or 0,
                "avg_wait_seconds": int(entries.avg_wait or 0),
                "longest_wait_seconds": longest_wait,
                "estimated_wait_seconds": estimate_wait_time(db, queue_id)
            },
            "agents": {
                "total": agents.total_agents or 0,
                "available": agents.available_agents or 0
            },
            "today": {
                "total_calls": today_stats.calls_today or 0,
                "avg_wait_seconds": int(today_stats.avg_wait_today or 0),
                "max_wait_seconds": int(today_stats.max_wait_today or 0),
                "abandoned": today_stats.abandoned_today or 0,
                "abandonment_rate": round((today_stats.abandoned_today or 0) / max(today_stats.calls_today or 1, 1) * 100, 1)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TWIML ENDPOINTS FOR QUEUING
# ============================================================================

@router.post("/twiml/enqueue")
@router.get("/twiml/enqueue")
async def enqueue_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    TwiML endpoint to put caller in queue.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        form_data = await request.form() if request.method == "POST" else {}

        queue_name = query_params.get("queue") or form_data.get("queue")
        call_sid = form_data.get("CallSid", "")
        caller = form_data.get("From", "Unknown")
        caller_name = form_data.get("CallerName", "")

        logger.info(f"Enqueueing call {call_sid} to queue {queue_name}")

        # Get queue settings
        queue = await db.execute(text("""
            SELECT id, name, friendly_name, max_queue_size, hold_music_url,
                   comfort_message, comfort_message_interval,
                   announce_position, announce_wait_time, position_announcement_interval,
                   overflow_action, overflow_target
            FROM call_queues
            WHERE name = :name AND is_active = TRUE
        """), {"name": queue_name}).fetchone()

        if not queue:
            # Queue not found - redirect to AI
            response = TeXMLResponse()
            response.say("Please hold while we connect you.", voice="Polly.Joanna")
            response.redirect("/api/v1/voice/incoming")
            return Response(content=str(response), media_type="application/xml")

        # Check queue capacity
        current_size = await db.execute(text("""
            SELECT COUNT(*) as count FROM queue_entries
            WHERE queue_id = :id AND status = 'waiting'
        """), {"id": queue.id}).fetchone()

        if current_size.count >= queue.max_queue_size:
            # Queue full - handle overflow
            return await handle_queue_overflow(queue, db)

        # Calculate position and estimated wait
        position = current_size.count + 1
        estimated_wait = estimate_wait_time(db, queue.id)

        # Create queue entry
        await db.execute(text("""
            INSERT INTO queue_entries
            (queue_id, call_sid, caller_phone, caller_name, position,
             estimated_wait_seconds, status)
            VALUES
            (:queue_id, :call_sid, :caller, :caller_name, :position,
             :estimated_wait, 'waiting')
        """), {
            "queue_id": queue.id,
            "call_sid": call_sid,
            "caller": caller,
            "caller_name": caller_name,
            "position": position,
            "estimated_wait": estimated_wait
        })
        await db.commit()

        # Build TwiML
        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        response = TeXMLResponse()

        # Initial announcement
        response.say(
            f"Thank you for calling. You are caller number {position} in the queue.",
            voice="Polly.Joanna"
        )

        if queue.announce_wait_time and estimated_wait > 0:
            wait_minutes = estimated_wait // 60
            if wait_minutes > 0:
                response.say(
                    f"Your estimated wait time is approximately {wait_minutes} {'minute' if wait_minutes == 1 else 'minutes'}.",
                    voice="Polly.Joanna"
                )

        # Enqueue with wait URL
        wait_url = f"{base_url}/api/v1/queues/twiml/wait?queue_id={queue.id}&position={position}"
        action_url = f"{base_url}/api/v1/queues/webhook/dequeue?queue_id={queue.id}&call_sid={call_sid}"

        enqueue = response.enqueue(
            queue.name,
            wait_url=wait_url,
            wait_url_method="POST",
            action=action_url
        )

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in enqueue TwiML: {e}")
        response = TeXMLResponse()
        response.say("We're experiencing technical difficulties. Please try again later.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/wait")
async def queue_wait_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    TwiML for queue wait music and periodic announcements.
    Called periodically while caller is waiting.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        form_data = await request.form()

        queue_id = query_params.get("queue_id")
        initial_position = int(query_params.get("position", "1"))
        queue_position = int(form_data.get("QueuePosition", initial_position))
        queue_time = int(form_data.get("QueueTime", "0"))

        # Get queue settings
        queue = await db.execute(text("""
            SELECT hold_music_url, comfort_message, comfort_message_interval,
                   announce_position, announce_wait_time, position_announcement_interval
            FROM call_queues WHERE id = :id
        """), {"id": queue_id}).fetchone()

        response = TeXMLResponse()

        # Periodic position announcement
        if queue and queue.announce_position:
            interval = queue.position_announcement_interval or 60
            if queue_time > 0 and queue_time % interval < 10:  # Announce every interval
                response.say(
                    f"You are currently number {queue_position} in the queue. "
                    f"Please continue to hold.",
                    voice="Polly.Joanna"
                )

        # Comfort message
        if queue and queue.comfort_message:
            interval = queue.comfort_message_interval or 30
            if queue_time > 0 and queue_time % interval < 10:
                response.say(queue.comfort_message, voice="Polly.Joanna")

        # Play hold music
        if queue and queue.hold_music_url:
            response.play(queue.hold_music_url, loop=1)
        else:
            # Default hold music
            response.play("/static/hold-music/classical.mp3", loop=1)

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in queue wait TwiML: {e}")
        response = TeXMLResponse()
        response.play("/static/hold-music/classical.mp3", loop=1)
        return Response(content=str(response), media_type="application/xml")


async def handle_queue_overflow(queue, db: Session):
    """Handle queue overflow based on settings"""
    from telephony.providers.telnyx.texml import TeXMLResponse

    response = TeXMLResponse()

    if queue.overflow_action == "voicemail":
        response.say(
            "All of our representatives are currently busy. "
            "Please leave a message after the beep and we will return your call.",
            voice="Polly.Joanna"
        )
        response.record(
            max_length=120,
            action="/api/v1/voice/voicemail-transcription",
            transcribe=True
        )

    elif queue.overflow_action == "transfer" and queue.overflow_target:
        response.say("Please hold while we transfer your call.", voice="Polly.Joanna")
        dial = response.dial(caller_id=os.getenv("TELNYX_PHONE_NUMBER", ""))
        dial.number(queue.overflow_target)

    elif queue.overflow_action == "callback":
        response.say(
            "All of our representatives are currently busy. "
            "We will call you back as soon as possible.",
            voice="Polly.Joanna"
        )
        # Could trigger callback scheduling here

    else:  # hangup
        response.say(
            "We're sorry, all of our representatives are currently busy. "
            "Please try again later.",
            voice="Polly.Joanna"
        )
        response.hangup()

    return Response(content=str(response), media_type="application/xml")


# ============================================================================
# WEBHOOK ENDPOINTS
# ============================================================================

@router.post("/webhook/dequeue")
async def dequeue_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    raw_body: bytes = Depends(require_telnyx_webhook),
):
    """
    Webhook when caller leaves queue (connected or abandoned).
    Webhook signature is verified by the require_telnyx_webhook dependency.
    """
    logger.info("Dequeue webhook received")

    try:
        query_params = request.query_params
        form_data = await request.form()

        queue_id = query_params.get("queue_id")
        call_sid = query_params.get("call_sid")
        dequeue_result = form_data.get("QueueResult", "")  # bridged, queue-full, hangup, etc.
        queue_time = form_data.get("QueueTime", "0")

        logger.info(f"Dequeue: call_sid={call_sid}, result={dequeue_result}, time={queue_time}")

        # Update queue entry
        status = "connected" if dequeue_result == "bridged" else "abandoned"
        await db.execute(text("""
            UPDATE queue_entries
            SET status = :status,
                actual_wait_seconds = :wait_time,
                updated_at = CURRENT_TIMESTAMP
            WHERE call_sid = :call_sid
        """), {
            "status": status,
            "wait_time": int(queue_time),
            "call_sid": call_sid
        })

        # Reposition remaining callers
        await db.execute(text("""
            UPDATE queue_entries
            SET position = position - 1
            WHERE queue_id = :queue_id
              AND status = 'waiting'
              AND position > (
                  SELECT position FROM queue_entries WHERE call_sid = :call_sid
              )
        """), {"queue_id": queue_id, "call_sid": call_sid})

        await db.commit()

        return {"status": "ok"}

    except SQLAlchemyError as e:
        logger.error(f"Error in dequeue webhook: {e}")
        return {"status": "error", "message": "Database error processing webhook"}


# ============================================================================
# AGENT ACTIONS
# ============================================================================

@router.post("/{queue_id}/take-next")
async def take_next_call(
    queue_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Agent action to take the next call from queue.
    Connects the oldest waiting caller to the agent.
    """
    try:
        provider = get_telephony_provider()
        if not provider:
            raise HTTPException(status_code=500, detail="Telephony not configured")

        # Get queue info
        queue = await db.execute(text("""
            SELECT name, telephony_queue_sid FROM call_queues WHERE id = :id
        """), {"id": queue_id}).fetchone()

        if not queue:
            raise HTTPException(status_code=404, detail="Queue not found")

        # Get next waiting call
        next_call = await db.execute(text("""
            SELECT id, call_sid, caller_phone, caller_name
            FROM queue_entries
            WHERE queue_id = :queue_id AND status = 'waiting'
            ORDER BY priority DESC, position ASC
            LIMIT 1
        """), {"queue_id": queue_id}).fetchone()

        if not next_call:
            return {"success": False, "message": "No calls waiting"}

        # Get agent's phone
        agent_phone = await db.execute(text("""
            SELECT phone, work_phone, mobile_phone FROM users WHERE id = :user_id
        """), {"user_id": current_user.id}).fetchone()

        if not agent_phone:
            raise HTTPException(status_code=400, detail="Agent has no phone configured")

        phone = agent_phone.mobile_phone or agent_phone.work_phone or agent_phone.phone

        # Bridge the call to agent by redirecting the queued call
        if queue.telephony_queue_sid and next_call.call_sid:
            try:
                # Redirect the queued call to dial the agent
                base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
                if base_url and not base_url.startswith("http"):
                    base_url = f"https://{base_url}"

                connect_url = f"{base_url}/api/v1/queues/twiml/connect-agent?phone={phone}&entry_id={next_call.id}"

                # Redirect the call to the connect-agent TwiML
                provider.update_call(next_call.call_sid, url=connect_url)

                # Update entry
                await db.execute(text("""
                    UPDATE queue_entries
                    SET status = 'connecting', connected_to_user_id = :user_id
                    WHERE id = :id
                """), {"id": next_call.id, "user_id": current_user.id})
                await db.commit()

                return {
                    "success": True,
                    "message": "Connecting call to agent",
                    "caller": next_call.caller_name or next_call.caller_phone,
                    "call_sid": next_call.call_sid
                }

            except Exception as telephony_error:
                logger.error(f"Telephony error connecting call: {telephony_error}")
                raise HTTPException(status_code=500, detail=str(telephony_error))

        return {"success": False, "message": "Queue not properly configured"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error taking next call: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/twiml/connect-agent")
async def connect_agent_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    TwiML to connect queued call to agent.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        phone = query_params.get("phone")
        entry_id = query_params.get("entry_id")

        response = TeXMLResponse()
        response.say("Connecting you now.", voice="Polly.Joanna")

        dial = response.dial(
            caller_id=os.getenv("TELNYX_PHONE_NUMBER", ""),
            action=f"/api/v1/queues/webhook/connect-status?entry_id={entry_id}"
        )
        dial.number(phone)

        return Response(content=str(response), media_type="application/xml")

    except SQLAlchemyError as e:
        logger.error(f"Error in connect agent TwiML: {e}")
        response = TeXMLResponse()
        response.say("Unable to connect. Please try again.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/webhook/connect-status")
async def connect_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    raw_body: bytes = Depends(require_telnyx_webhook),
):
    """
    Webhook for agent connection status.
    Webhook signature is verified by the require_telnyx_webhook dependency.
    """
    logger.info("Connect status webhook received")

    try:
        query_params = request.query_params
        form_data = await request.form()

        entry_id = query_params.get("entry_id")
        dial_status = form_data.get("DialCallStatus", "")

        logger.info(f"Connect status: entry_id={entry_id}, status={dial_status}")

        if dial_status in ["completed", "answered"]:
            await db.execute(text("""
                UPDATE queue_entries
                SET status = 'connected', connected_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": entry_id})
        else:
            # Agent didn't answer - put back in queue
            await db.execute(text("""
                UPDATE queue_entries
                SET status = 'waiting', connected_to_user_id = NULL
                WHERE id = :id
            """), {"id": entry_id})

        await db.commit()
        return {"status": "ok"}

    except SQLAlchemyError as e:
        logger.error(f"Error in connect status webhook: {e}")
        return {"status": "error"}
