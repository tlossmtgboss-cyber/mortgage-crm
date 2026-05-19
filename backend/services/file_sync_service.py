"""
File Sync Service — Real-time loan file state synchronization.

Uses Redis pub/sub for cross-instance event distribution and in-process
WebSocket fan-out for <500ms delivery to every collaborator viewing a file.

Channel naming: ``file:{file_id}:updates``

Design choices
--------------
* Redis is optional.  When unavailable (local dev, Railway without Redis add-on),
  the service degrades to in-process-only fan-out — still real-time within one
  dyno, just not cross-instance.
* All public methods are async and safe to call from any route handler.
* FieldChangeTracker writes immutable audit rows for SOC 2 / TRID compliance.
  Each record includes user_id, role, action_type, and UTC timestamp.
* Tenant isolation is enforced: every event carries ``organization_id`` and
  subscribers are keyed ``(org_id, file_id)``.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis connection (lazy init — Railway may or may not have Redis)
# ---------------------------------------------------------------------------

_redis_client = None
_redis_lock = asyncio.Lock()


async def _get_redis():
    """Return an async Redis client or ``None`` if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    async with _redis_lock:
        # Double-check after acquiring lock
        if _redis_client is not None:
            return _redis_client

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.info("REDIS_URL not set — file sync running in local-only mode")
            return None

        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                max_connections=5,
                retry_on_timeout=True,
            )
            await client.ping()
            _redis_client = client
            safe_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url
            logger.info(f"Redis connected for file sync: {safe_url}")
        except Exception as e:
            logger.warning(f"Redis not available for file sync: {e}")
            _redis_client = None

    return _redis_client


def _channel_name(file_id: int) -> str:
    """Canonical Redis channel for a loan file."""
    return f"file:{file_id}:updates"


# ---------------------------------------------------------------------------
# In-process connection manager (single-dyno fan-out)
# ---------------------------------------------------------------------------

class _FileConnectionManager:
    """
    Tracks active WebSocket connections per (org_id, file_id).

    Thread-safe via asyncio.Lock.  Used for immediate in-process delivery
    and as the local leg of Redis pub/sub fan-out.
    """

    def __init__(self):
        # (org_id, file_id) -> {user_id -> set of WebSocket}
        self._connections: Dict[tuple, Dict[int, Set[WebSocket]]] = {}
        self._metadata: Dict[WebSocket, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        file_id: int,
        user_id: int,
        org_id: int,
        websocket: WebSocket,
    ) -> None:
        """Register a WebSocket for file updates."""
        async with self._lock:
            key = (org_id, file_id)
            if key not in self._connections:
                self._connections[key] = {}
            if user_id not in self._connections[key]:
                self._connections[key][user_id] = set()
            self._connections[key][user_id].add(websocket)

            self._metadata[websocket] = {
                "file_id": file_id,
                "user_id": user_id,
                "org_id": org_id,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }

        logger.info(
            f"User {user_id} subscribed to file {file_id} (org={org_id})"
        )

    async def unsubscribe(self, websocket: WebSocket) -> None:
        """Remove a WebSocket on disconnect."""
        async with self._lock:
            meta = self._metadata.pop(websocket, None)
            if meta is None:
                return
            key = (meta["org_id"], meta["file_id"])
            user_id = meta["user_id"]
            user_sockets = self._connections.get(key, {}).get(user_id)
            if user_sockets:
                user_sockets.discard(websocket)
                if not user_sockets:
                    del self._connections[key][user_id]
                if not self._connections.get(key):
                    self._connections.pop(key, None)

        if meta:
            logger.info(
                f"User {meta['user_id']} unsubscribed from file {meta['file_id']}"
            )

    async def get_subscribers(self, file_id: int, org_id: int) -> List[Dict]:
        """Return metadata for active subscribers on a file."""
        async with self._lock:
            key = (org_id, file_id)
            user_map = self._connections.get(key, {})
            result = []
            for uid, sockets in user_map.items():
                result.append({
                    "user_id": uid,
                    "connection_count": len(sockets),
                })
            return result

    async def broadcast(
        self,
        file_id: int,
        org_id: int,
        message: dict,
        exclude_user_id: Optional[int] = None,
    ) -> int:
        """
        Send *message* to every subscriber on *(org_id, file_id)*.

        Returns the number of WebSockets that received the message.
        Silently removes dead connections.
        """
        async with self._lock:
            key = (org_id, file_id)
            user_map = self._connections.get(key, {})
            # Snapshot to avoid mutation during iteration
            targets: List[WebSocket] = []
            for uid, sockets in user_map.items():
                if uid == exclude_user_id:
                    continue
                targets.extend(sockets)

        sent = 0
        dead: List[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                dead.append(ws)

        # Clean up dead connections outside broadcast lock
        for ws in dead:
            await self.unsubscribe(ws)

        return sent


# Module-level singleton
_conn_manager = _FileConnectionManager()


# ---------------------------------------------------------------------------
# Redis pub/sub listener (one background task per instance)
# ---------------------------------------------------------------------------

_listener_task: Optional[asyncio.Task] = None
_listener_lock = asyncio.Lock()


async def _ensure_redis_listener():
    """Start the background Redis subscriber if not already running."""
    global _listener_task

    redis_client = await _get_redis()
    if redis_client is None:
        return

    async with _listener_lock:
        if _listener_task is not None and not _listener_task.done():
            return
        _listener_task = asyncio.create_task(_redis_listener_loop(redis_client))
        logger.info("Redis pub/sub listener started for file sync")


async def _redis_listener_loop(redis_client):
    """
    Subscribe to ``file:*:updates`` pattern and fan-out to local WebSockets.

    Reconnects automatically on transient failures.
    """
    import redis.asyncio as aioredis

    while True:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.psubscribe("file:*:updates")
            logger.info("Redis pub/sub pattern subscription active: file:*:updates")

            async for raw_message in pubsub.listen():
                if raw_message["type"] not in ("pmessage",):
                    continue
                try:
                    payload = json.loads(raw_message["data"])
                    file_id = payload.get("file_id")
                    org_id = payload.get("organization_id", 0)
                    origin = payload.get("_origin_instance")

                    # Skip messages published by this instance (already fanned out)
                    if origin == _instance_id:
                        continue

                    if file_id is not None:
                        count = await _conn_manager.broadcast(
                            file_id, org_id, payload
                        )
                        if count:
                            logger.debug(
                                f"Redis fan-out: file {file_id} -> {count} local sockets"
                            )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Malformed file sync message: {e}")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
            return
        except Exception as e:
            logger.error(f"Redis listener error, reconnecting in 3s: {e}")
            await asyncio.sleep(3)


# Unique per-process identifier to deduplicate messages
_instance_id = uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# FileSyncService — public API
# ---------------------------------------------------------------------------

class FileSyncService:
    """
    Real-time file state sync via Redis pub/sub + in-process WebSocket fan-out.

    Usage from route handlers::

        await FileSyncService.publish_file_update(
            file_id=loan.id,
            event_type="status_change",
            data={"stage": "PROCESSING", "previous_stage": "APPLICATION"},
            user_id=current_user.id,
            organization_id=current_user.organization_id,
        )

    Collaborators subscribed via ``subscribe_to_file`` receive the event
    on their WebSocket within 500ms.
    """

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    @staticmethod
    async def publish_file_update(
        file_id: int,
        event_type: str,
        data: dict,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ) -> bool:
        """
        Publish an update to all collaborators on a loan file.

        Parameters
        ----------
        file_id : int
            The loan (file) primary key.
        event_type : str
            Descriptor such as ``status_change``, ``document_uploaded``,
            ``condition_cleared``, ``communication_logged``.
        data : dict
            Event-specific payload.
        user_id : int, optional
            The user who triggered the change (excluded from local fan-out).
        organization_id : int, optional
            Tenant id for isolation.

        Returns
        -------
        bool
            ``True`` if the event was published (at least locally).
        """
        org_id = organization_id or 0

        message = {
            "type": "file_update",
            "event": event_type,
            "file_id": file_id,
            "organization_id": org_id,
            "triggered_by": user_id,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": uuid.uuid4().hex,
            "_origin_instance": _instance_id,
        }

        # 1. In-process fan-out (immediate — same dyno)
        local_count = await _conn_manager.broadcast(
            file_id, org_id, message, exclude_user_id=user_id
        )

        # 2. Redis pub/sub (cross-instance)
        redis_client = await _get_redis()
        if redis_client is not None:
            try:
                await redis_client.publish(
                    _channel_name(file_id), json.dumps(message)
                )
                await _ensure_redis_listener()
            except Exception as e:
                logger.error(f"Redis publish failed for file {file_id}: {e}")

        logger.debug(
            f"File update published: file={file_id} event={event_type} "
            f"local_recipients={local_count}"
        )
        return True

    @staticmethod
    async def publish_field_change(
        file_id: int,
        field_name: str,
        old_value: Any,
        new_value: Any,
        changed_by: int,
        organization_id: Optional[int] = None,
    ) -> bool:
        """
        Publish a specific field-level change for real-time UI diffing.

        Wraps ``publish_file_update`` with a ``field_change`` event type and
        structured before/after payload.
        """
        data = {
            "field": field_name,
            "old_value": _serialize_value(old_value),
            "new_value": _serialize_value(new_value),
            "changed_by": changed_by,
        }
        return await FileSyncService.publish_file_update(
            file_id=file_id,
            event_type="field_change",
            data=data,
            user_id=changed_by,
            organization_id=organization_id,
        )

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    @staticmethod
    async def subscribe_to_file(
        file_id: int,
        user_id: int,
        organization_id: int,
        websocket: WebSocket,
    ) -> None:
        """
        Register a WebSocket connection for real-time updates on a file.

        Call this after ``websocket.accept()`` in your WebSocket route handler.
        Ensures the Redis listener is running if Redis is available.
        """
        await _conn_manager.subscribe(file_id, user_id, organization_id, websocket)

        # Track presence in Redis (if available) for cross-instance awareness
        redis_client = await _get_redis()
        if redis_client is not None:
            try:
                presence_key = f"file:{file_id}:presence"
                await redis_client.hset(
                    presence_key,
                    str(user_id),
                    json.dumps({
                        "instance": _instance_id,
                        "connected_at": datetime.now(timezone.utc).isoformat(),
                    }),
                )
                # Expire presence after 1 hour (stale-connection guard)
                await redis_client.expire(presence_key, 3600)
            except Exception as e:
                logger.warning(f"Redis presence update failed: {e}")

        # Ensure cross-instance listener is active
        await _ensure_redis_listener()

    @staticmethod
    async def unsubscribe_from_file(websocket: WebSocket) -> None:
        """Remove a WebSocket from file updates (call on disconnect)."""
        meta = _conn_manager._metadata.get(websocket)
        await _conn_manager.unsubscribe(websocket)

        # Remove presence from Redis
        if meta:
            redis_client = await _get_redis()
            if redis_client is not None:
                try:
                    presence_key = f"file:{meta['file_id']}:presence"
                    await redis_client.hdel(presence_key, str(meta["user_id"]))
                except Exception as e:
                    logger.warning(f"Redis presence cleanup failed: {e}")

    @staticmethod
    async def get_file_subscribers(
        file_id: int, organization_id: int = 0
    ) -> List[Dict]:
        """
        Get list of active subscribers on a file.

        Merges local connections with Redis presence data for cross-instance
        visibility.
        """
        local = await _conn_manager.get_subscribers(file_id, organization_id)

        redis_client = await _get_redis()
        if redis_client is not None:
            try:
                presence_key = f"file:{file_id}:presence"
                raw = await redis_client.hgetall(presence_key)
                remote_user_ids = set()
                for uid_str, val in raw.items():
                    try:
                        info = json.loads(val)
                        if info.get("instance") != _instance_id:
                            remote_user_ids.add(int(uid_str))
                    except (json.JSONDecodeError, ValueError):
                        pass

                # Merge: add remote-only users
                local_user_ids = {s["user_id"] for s in local}
                for uid in remote_user_ids - local_user_ids:
                    local.append({
                        "user_id": uid,
                        "connection_count": 1,
                        "remote": True,
                    })
            except Exception as e:
                logger.warning(f"Redis presence query failed: {e}")

        return local


# ---------------------------------------------------------------------------
# FieldChangeTracker — immutable audit trail (SOC 2)
# ---------------------------------------------------------------------------

class FieldChangeTracker:
    """
    Tracks field-level changes for audit trail and SOC 2 compliance.

    Every mutation is recorded as an immutable row in ``field_change_audit``
    (or the existing ``audit_logs`` table as a fallback).  Each record
    includes user_id, role, UTC timestamp, and action_type.
    """

    @staticmethod
    async def record_change(
        file_id: int,
        user_id: int,
        role: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        action_type: str,
        db,
    ) -> dict:
        """
        Record an immutable field-level change.

        Parameters
        ----------
        file_id : int
            Loan / file primary key.
        user_id : int
            User who made the change.
        role : str
            User's role at time of change (e.g. ``loan_officer``, ``processor``).
        field_name : str
            Column or logical field name.
        old_value : Any
            Value before the change (will be JSON-serialized).
        new_value : Any
            Value after the change (will be JSON-serialized).
        action_type : str
            Semantic action — ``update``, ``create``, ``delete``,
            ``stage_transition``, ``document_upload``, ``condition_clear``, etc.
        db : Session
            SQLAlchemy session (from ``get_db()``).

        Returns
        -------
        dict
            The recorded audit entry with ``id`` and ``recorded_at``.
        """
        now = datetime.now(timezone.utc)
        serialized_old = _serialize_value(old_value)
        serialized_new = _serialize_value(new_value)

        entry = {
            "file_id": file_id,
            "user_id": user_id,
            "role": role,
            "field_name": field_name,
            "old_value": serialized_old,
            "new_value": serialized_new,
            "action_type": action_type,
            "recorded_at": now.isoformat(),
        }

        # Write to audit_logs table via raw SQL for reliability
        # (avoids model import circular deps and works even if the
        # field_change_audit table hasn't been migrated yet)
        try:
            from sqlalchemy import text

            result = db.execute(
                text("""
                    INSERT INTO audit_logs
                        (user_id, changed_by_id, change_type, entity_type,
                         entity_id, before_state, after_state, reason, timestamp)
                    VALUES
                        (:user_id, :user_id, :change_type, 'loan_file',
                         :entity_id, :before_state, :after_state, :reason,
                         :timestamp)
                    RETURNING id
                """),
                {
                    "user_id": user_id,
                    "change_type": action_type,
                    "entity_id": file_id,
                    "before_state": json.dumps({
                        "field": field_name,
                        "value": serialized_old,
                    }),
                    "after_state": json.dumps({
                        "field": field_name,
                        "value": serialized_new,
                    }),
                    "reason": f"field_change:{field_name} by role:{role}",
                    "timestamp": now,
                },
            )
            row = result.fetchone()
            db.commit()

            entry["id"] = row[0] if row else None
            logger.debug(
                f"Field change recorded: file={file_id} field={field_name} "
                f"action={action_type} by user={user_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to record field change audit: {e}", exc_info=True
            )
            db.rollback()
            entry["id"] = None
            entry["error"] = str(e)

        return entry

    @staticmethod
    async def get_file_history(
        file_id: int,
        db,
        limit: int = 50,
        field_name: Optional[str] = None,
    ) -> List[dict]:
        """
        Retrieve the audit trail for a loan file.

        Parameters
        ----------
        file_id : int
            Loan primary key.
        db : Session
            SQLAlchemy session.
        limit : int
            Max rows to return (default 50).
        field_name : str, optional
            Filter to a specific field.

        Returns
        -------
        list[dict]
            Audit entries ordered newest-first.
        """
        try:
            from sqlalchemy import text

            params: dict = {"file_id": file_id, "limit": limit}
            field_filter = ""
            if field_name:
                field_filter = "AND reason LIKE :field_pattern"
                params["field_pattern"] = f"field_change:{field_name}%"

            rows = db.execute(
                text(f"""
                    SELECT id, user_id, changed_by_id, change_type,
                           before_state, after_state, reason, timestamp
                    FROM audit_logs
                    WHERE entity_type = 'loan_file'
                      AND entity_id = :file_id
                      {field_filter}
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                params,
            ).fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "user_id": row[1],
                    "changed_by_id": row[2],
                    "action_type": row[3],
                    "before_state": json.loads(row[4]) if row[4] else None,
                    "after_state": json.loads(row[5]) if row[5] else None,
                    "reason": row[6],
                    "recorded_at": row[7].isoformat() if row[7] else None,
                })
            return results

        except Exception as e:
            logger.error(f"Failed to query file history: {e}", exc_info=True)
            return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_value(value: Any) -> Any:
    """
    Convert a value to a JSON-safe representation.

    Handles datetime, Decimal, and other common SQLAlchemy column types.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return str(value)
    except ImportError:
        pass
    # Fallback: force to string
    return str(value)
