"""
Distributed Lock Service - Redis-based locking for multi-worker safety.

In a multi-worker deployment (e.g., 2+ Gunicorn workers), Python's threading.Lock()
only protects within a single process. Two workers can simultaneously pass the lock
check and create conflicting bookings.

This service provides Redis-based distributed locks that work across all workers:
  - acquire_slot_lock():    Lock a specific user+timeslot during booking
  - acquire_booking_lock(): Org-level lock for booking operations
  - is_slot_locked():       Check if a slot is currently locked
  - distributed_lock():     Async context manager for autonomous agent locking

Graceful degradation:
  - If Redis is unavailable, the service logs a warning and falls through.
    The caller's SELECT FOR UPDATE provides a database-level safety net.
  - This is defense-in-depth: Redis lock catches the race early (before DB round-trip),
    SELECT FOR UPDATE catches it at the DB level if Redis is down.

Usage:
    # Slot/booking locks (synchronous)
    from services.distributed_lock import get_lock_service

    lock_svc = get_lock_service()
    with lock_svc.acquire_slot_lock(user_id=42, start_time=dt):
        # Check for conflicts + create appointment inside the lock
        ...

    # Autonomous agent / async locks
    from services.distributed_lock import distributed_lock

    async with distributed_lock("agent:lead_nurturer", ttl=300):
        # Only one instance across all replicas runs this block
        ...
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Lua script for safe lock release.
# Only deletes the key if the stored value matches our lock token.
# This prevents a slow worker from accidentally releasing a lock
# that was acquired by a different worker after the original TTL expired.
_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class DistributedLockError(Exception):
    """Raised when a distributed lock cannot be acquired."""
    pass


class DistributedLockService:
    """Redis-based distributed locking for multi-worker safety.

    Thread-safe: each lock acquisition uses a unique token, so multiple
    threads/coroutines can hold different locks simultaneously.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = None
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis_checked = False
        self._release_script = None  # Cached Lua script object
        self.default_ttl = 10  # seconds — auto-expire to prevent deadlocks

    def _get_redis(self):
        """Lazy-initialize Redis connection. Returns None if unavailable."""
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            import redis as redis_lib
            self._redis = redis_lib.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=3,
            )
            self._redis.ping()
            # Pre-register the Lua script for atomic release
            self._release_script = self._redis.register_script(_RELEASE_LOCK_LUA)
            logger.info("DistributedLockService: connected to Redis")
        except Exception as e:
            logger.warning(
                f"DistributedLockService: Redis unavailable ({e}). "
                "Distributed locking disabled — relying on SELECT FOR UPDATE only."
            )
            self._redis = None
        return self._redis

    def _acquire(self, lock_key: str, lock_value: str, ttl: int, timeout: float) -> bool:
        """Try to acquire a Redis lock with retry until timeout.

        Uses SET NX EX for atomic lock acquisition:
          - NX: only set if key does not exist
          - EX: auto-expire after ttl seconds (deadlock prevention)

        Returns True if lock was acquired, False otherwise.
        """
        r = self._get_redis()
        if r is None:
            return False  # Redis unavailable — caller should fall through

        deadline = time.monotonic() + timeout
        retry_interval = 0.05  # Start with 50ms retries

        while time.monotonic() < deadline:
            try:
                acquired = r.set(lock_key, lock_value, nx=True, ex=ttl)
                if acquired:
                    return True
            except Exception as e:
                logger.warning(f"DistributedLockService: Redis error during acquire: {e}")
                return False  # Don't retry on connection errors

            # Exponential backoff with cap
            time.sleep(retry_interval)
            retry_interval = min(retry_interval * 1.5, 0.3)

        return False

    def _release(self, lock_key: str, lock_value: str) -> bool:
        """Release a lock, but only if we still own it (compare-and-delete via Lua).

        Returns True if the lock was released, False if it was already expired
        or owned by someone else.
        """
        r = self._get_redis()
        if r is None:
            return False

        try:
            if self._release_script is not None:
                result = self._release_script(keys=[lock_key], args=[lock_value])
            else:
                # Fallback: non-atomic check-and-delete (race window, but better than nothing)
                stored = r.get(lock_key)
                if stored == lock_value:
                    r.delete(lock_key)
                    result = 1
                else:
                    result = 0
            return result == 1
        except Exception as e:
            logger.warning(f"DistributedLockService: Redis error during release: {e}")
            return False

    @contextmanager
    def acquire_slot_lock(
        self,
        user_id,
        start_time: datetime,
        ttl: int = None,
        timeout: float = 5.0,
    ):
        """Lock a specific time slot for a specific user during booking.

        Args:
            user_id: The assigned user/LO ID for the appointment.
            start_time: The start time of the slot being booked.
            ttl: Lock auto-expiry in seconds (default: self.default_ttl).
            timeout: Max seconds to wait for lock acquisition.

        Yields:
            True if lock was acquired (Redis available),
            False if Redis was unavailable (caller should rely on DB-level locking).

        Raises:
            DistributedLockError: If the lock could not be acquired within the timeout
                                  (another booking is in progress for this exact slot).
        """
        ttl = ttl or self.default_ttl
        lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"
        lock_value = str(uuid.uuid4())

        r = self._get_redis()
        if r is None:
            # Redis unavailable — fall through, rely on SELECT FOR UPDATE
            logger.warning(
                "DistributedLockService: Redis unavailable for slot lock. "
                "Falling back to database-level locking only."
            )
            yield False
            return

        acquired = self._acquire(lock_key, lock_value, ttl, timeout)
        if not acquired:
            raise DistributedLockError(
                f"Could not acquire slot lock for user {user_id} at {start_time.isoformat()}. "
                "Another booking may be in progress for this time slot."
            )

        try:
            yield True
        finally:
            released = self._release(lock_key, lock_value)
            if not released:
                logger.warning(
                    f"DistributedLockService: Failed to release slot lock {lock_key}. "
                    f"Lock may have expired (TTL={ttl}s). This is non-fatal."
                )

    @contextmanager
    def acquire_booking_lock(
        self,
        org_id,
        ttl: int = None,
        timeout: float = 5.0,
    ):
        """Org-level lock for booking operations.

        This is a broader lock used to serialize booking operations within an org.
        Use acquire_slot_lock() for slot-specific locking when you know the exact
        user+time combination.

        Args:
            org_id: Organization ID to lock bookings for.
            ttl: Lock auto-expiry in seconds (default: self.default_ttl).
            timeout: Max seconds to wait for lock acquisition.

        Yields:
            True if lock was acquired, False if Redis unavailable.

        Raises:
            DistributedLockError: If lock could not be acquired within timeout.
        """
        ttl = ttl or self.default_ttl
        lock_key = f"booking_lock:org:{org_id}"
        lock_value = str(uuid.uuid4())

        r = self._get_redis()
        if r is None:
            logger.warning(
                "DistributedLockService: Redis unavailable for booking lock. "
                "Falling back to database-level locking only."
            )
            yield False
            return

        acquired = self._acquire(lock_key, lock_value, ttl, timeout)
        if not acquired:
            raise DistributedLockError(
                f"Could not acquire booking lock for org {org_id}. "
                "High booking volume — please retry."
            )

        try:
            yield True
        finally:
            released = self._release(lock_key, lock_value)
            if not released:
                logger.warning(
                    f"DistributedLockService: Failed to release booking lock {lock_key}. "
                    f"Lock may have expired (TTL={ttl}s)."
                )

    def is_slot_locked(self, user_id, start_time: datetime) -> bool:
        """Check if a specific time slot is currently locked.

        Useful for availability checks — if a slot is locked, it's actively
        being booked and should be shown as unavailable.

        Returns False if Redis is unavailable (assume not locked).
        """
        r = self._get_redis()
        if r is None:
            return False

        lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"
        try:
            return r.exists(lock_key) > 0
        except Exception as e:
            logger.warning(f"DistributedLockService: Redis error in is_slot_locked: {e}")
            return False


# =============================================================================
# Singleton with lazy initialization
# =============================================================================

_lock_service: Optional[DistributedLockService] = None


def get_lock_service() -> DistributedLockService:
    """Get or create the singleton DistributedLockService.

    Thread-safe via Python's GIL for the initial assignment.
    The Redis connection itself is lazily established on first use.
    """
    global _lock_service
    if _lock_service is None:
        _lock_service = DistributedLockService()
    return _lock_service


# =============================================================================
# Async distributed lock for autonomous agents
# =============================================================================
#
# When Railway scales to 2+ instances, the same autonomous agent can fire on
# every replica simultaneously. The local threading.Semaphore in loop.py only
# guards within a single process. This async context manager uses Redis SETNX
# to ensure exactly one replica executes a given agent at a time.
#
# Design:
#   - SETNX + EX (atomic set-if-not-exists with expiry) — simple, proven
#   - Heartbeat task extends TTL while the body is still running
#   - Graceful fallback: if Redis is unavailable, log warning and proceed
#     (local semaphore still limits within-process concurrency)
#   - Compare-and-delete on release via Lua script (same as slot locks)
#
# Usage:
#   async with distributed_lock("agent:lead_nurturer", ttl=300):
#       await do_work()
#
#   # Non-blocking check (skip if another replica holds the lock):
#   async with distributed_lock("agent:cost_optimization", ttl=60, block=False) as acquired:
#       if not acquired:
#           return  # another replica is running this agent
#       await do_work()
# =============================================================================

# Local fallback: track which lock keys are held in this process so that
# even without Redis, we don't run the same agent twice in one process.
_local_locks: Set[str] = set()
_local_lock_guard = threading.Lock()

# Default heartbeat interval — extend lock TTL every ttl/3 seconds
_HEARTBEAT_DIVISOR = 3


@asynccontextmanager
async def distributed_lock(
    key: str,
    ttl: int = 300,
    block: bool = True,
    timeout: float = 10.0,
    extend: bool = True,
):
    """Async context manager providing a Redis-based distributed lock.

    Args:
        key: Lock identifier (e.g. "agent:lead_nurturer" or "agent:pipeline_monitor:org:7").
             Automatically prefixed with "dlock:" to avoid collision with other Redis keys.
        ttl: Lock auto-expiry in seconds. Default 300 (5 minutes). Prevents deadlocks
             if the holder crashes without releasing.
        block: If True (default), retry until timeout. If False, yield False immediately
               when the lock is already held.
        timeout: Max seconds to wait when block=True. Ignored when block=False.
        extend: If True (default), a background task extends the TTL at ttl/3 intervals
                while the body is executing. Prevents premature expiry for long-running
                agents. Set to False for short, bounded operations.

    Yields:
        True if the lock was acquired (Redis or local fallback).
        False if the lock could not be acquired (block=False mode only).

    Example:
        async with distributed_lock("agent:lead_nurturer", ttl=300) as acquired:
            if not acquired:
                return  # only reachable when block=False
            await run_agent_logic()
    """
    lock_key = f"dlock:{key}"
    lock_value = str(uuid.uuid4())
    lock_svc = get_lock_service()
    redis_client = lock_svc._get_redis()
    acquired = False
    heartbeat_task: Optional[asyncio.Task] = None

    try:
        if redis_client is not None:
            # --- Redis path: SETNX with retry ---
            acquired = await _async_acquire(redis_client, lock_key, lock_value, ttl, block, timeout)

            if not acquired and not block:
                yield False
                return
            elif not acquired and block:
                logger.warning(
                    "distributed_lock(%s): could not acquire within %.1fs timeout — "
                    "proceeding without lock (fallback to local guard)",
                    key, timeout,
                )
                # Fall through to local lock below
        else:
            logger.warning(
                "distributed_lock(%s): Redis unavailable — using local-only locking",
                key,
            )

        # --- Local fallback (also used as belt-and-suspenders with Redis) ---
        if not acquired:
            with _local_lock_guard:
                if lock_key in _local_locks:
                    if not block:
                        yield False
                        return
                    # Already running locally — skip
                    logger.info(
                        "distributed_lock(%s): already held locally — skipping",
                        key,
                    )
                    yield False
                    return
                _local_locks.add(lock_key)
        else:
            # Also register locally so same-process callers see it
            with _local_lock_guard:
                _local_locks.add(lock_key)

        # --- Start heartbeat if we hold the Redis lock and extend=True ---
        if acquired and extend and redis_client is not None:
            heartbeat_task = asyncio.create_task(
                _heartbeat_loop(redis_client, lock_key, lock_value, ttl),
                name=f"dlock-heartbeat:{key}",
            )

        yield True

    finally:
        # --- Cleanup: cancel heartbeat, release locks ---
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        # Release Redis lock (compare-and-delete)
        if acquired and redis_client is not None:
            try:
                lock_svc._release(lock_key, lock_value)
            except Exception as e:
                logger.warning("distributed_lock(%s): failed to release Redis lock: %s", key, e)

        # Release local lock
        with _local_lock_guard:
            _local_locks.discard(lock_key)


async def _async_acquire(
    redis_client,
    lock_key: str,
    lock_value: str,
    ttl: int,
    block: bool,
    timeout: float,
) -> bool:
    """Attempt to acquire a Redis lock, optionally retrying until timeout.

    Runs the blocking Redis SET NX call in a thread executor to avoid blocking
    the event loop.
    """
    loop = asyncio.get_running_loop()

    def _try_set():
        try:
            return redis_client.set(lock_key, lock_value, nx=True, ex=ttl)
        except Exception as e:
            logger.warning("distributed_lock: Redis SET failed: %s", e)
            return None

    # First attempt
    result = await loop.run_in_executor(None, _try_set)
    if result:
        return True

    if not block:
        return False

    # Retry with exponential backoff
    deadline = time.monotonic() + timeout
    interval = 0.05
    while time.monotonic() < deadline:
        await asyncio.sleep(interval)
        result = await loop.run_in_executor(None, _try_set)
        if result:
            return True
        interval = min(interval * 1.5, 0.5)

    return False


async def _heartbeat_loop(redis_client, lock_key: str, lock_value: str, ttl: int):
    """Periodically extend the lock TTL while the holder is still running.

    Runs every ttl/3 seconds. Uses a Lua script to only extend if we still
    own the lock (compare value before EXPIRE). This prevents extending a
    lock that was already acquired by another replica after our TTL expired.
    """
    extend_interval = max(ttl // _HEARTBEAT_DIVISOR, 1)

    # Lua script: extend TTL only if we still own the lock
    extend_lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    loop = asyncio.get_running_loop()

    def _extend():
        try:
            script = redis_client.register_script(extend_lua)
            return script(keys=[lock_key], args=[lock_value, str(ttl)])
        except Exception as e:
            logger.warning("distributed_lock heartbeat: extend failed: %s", e)
            return 0

    try:
        while True:
            await asyncio.sleep(extend_interval)
            result = await loop.run_in_executor(None, _extend)
            if not result:
                logger.info(
                    "distributed_lock heartbeat: lock %s no longer owned — stopping heartbeat",
                    lock_key,
                )
                break
    except asyncio.CancelledError:
        pass  # Normal shutdown when the context manager exits
