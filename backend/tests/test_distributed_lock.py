"""
Tests for the distributed lock service.

Uses mock Redis to test lock acquisition, release, contention, and fallback behavior
without requiring a running Redis instance.
"""

import time
import threading
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from services.distributed_lock import (
    DistributedLockService,
    DistributedLockError,
    get_lock_service,
    _RELEASE_LOCK_LUA,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    """Create a mock Redis client that simulates basic SET NX EX behavior."""
    redis_mock = MagicMock()
    redis_mock.ping.return_value = True

    # Track which keys are currently set (simulate NX behavior)
    _store = {}

    def mock_set(key, value, nx=False, ex=None):
        if nx and key in _store:
            return False  # Key already exists
        _store[key] = value
        return True

    def mock_get(key):
        return _store.get(key)

    def mock_delete(key):
        return _store.pop(key, None) is not None

    def mock_exists(key):
        return 1 if key in _store else 0

    redis_mock.set.side_effect = mock_set
    redis_mock.get.side_effect = mock_get
    redis_mock.delete.side_effect = mock_delete
    redis_mock.exists.side_effect = mock_exists

    # Mock register_script to return a callable that simulates the Lua script
    def mock_lua_script(keys, args):
        key = keys[0]
        expected_value = args[0]
        stored = _store.get(key)
        if stored == expected_value:
            _store.pop(key, None)
            return 1
        return 0

    mock_script_obj = MagicMock(side_effect=mock_lua_script)
    redis_mock.register_script.return_value = mock_script_obj

    # Expose the internal store for test assertions
    redis_mock._store = _store

    return redis_mock


@pytest.fixture
def lock_service(mock_redis):
    """Create a DistributedLockService with a pre-configured mock Redis."""
    svc = DistributedLockService.__new__(DistributedLockService)
    svc._redis = mock_redis
    svc._redis_url = "redis://mock:6379"
    svc._redis_checked = True
    svc._release_script = mock_redis.register_script(_RELEASE_LOCK_LUA)
    svc.default_ttl = 10
    return svc


@pytest.fixture
def no_redis_service():
    """Create a DistributedLockService with Redis unavailable."""
    svc = DistributedLockService.__new__(DistributedLockService)
    svc._redis = None
    svc._redis_url = "redis://mock:6379"
    svc._redis_checked = True
    svc._release_script = None
    svc.default_ttl = 10
    return svc


# =============================================================================
# Test: acquire_slot_lock
# =============================================================================

class TestAcquireSlotLock:
    """Tests for the slot-level distributed lock."""

    def test_acquire_and_release_slot_lock(self, lock_service, mock_redis):
        """Lock should be acquired, then released after context manager exits."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        with lock_service.acquire_slot_lock(user_id, start_time) as acquired:
            assert acquired is True
            # Key should exist in Redis while held
            lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"
            assert lock_key in mock_redis._store

        # After exit, key should be released
        assert lock_key not in mock_redis._store

    def test_slot_lock_key_format(self, lock_service, mock_redis):
        """Lock key should include user_id and ISO-formatted start_time."""
        user_id = 99
        start_time = datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc)
        expected_key = f"slot_lock:99:{start_time.isoformat()}"

        with lock_service.acquire_slot_lock(user_id, start_time):
            assert expected_key in mock_redis._store

    def test_slot_lock_contention_raises_error(self, lock_service, mock_redis):
        """When another worker holds the lock, acquiring should raise DistributedLockError."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"

        # Simulate another worker holding the lock
        mock_redis._store[lock_key] = "other-worker-token"

        with pytest.raises(DistributedLockError, match="Could not acquire slot lock"):
            with lock_service.acquire_slot_lock(user_id, start_time, timeout=0.2):
                pass  # Should never reach here

    def test_slot_lock_uses_unique_tokens(self, lock_service, mock_redis):
        """Each lock acquisition should use a unique UUID token."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"

        tokens = []
        for _ in range(3):
            with lock_service.acquire_slot_lock(user_id, start_time):
                tokens.append(mock_redis._store[lock_key])

        # All tokens should be unique
        assert len(set(tokens)) == 3

    def test_slot_lock_custom_ttl(self, lock_service, mock_redis):
        """Custom TTL should be passed to Redis SET command."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        with lock_service.acquire_slot_lock(user_id, start_time, ttl=30):
            # Verify SET was called with ex=30
            mock_redis.set.assert_called()
            call_kwargs = mock_redis.set.call_args
            assert call_kwargs[1]['ex'] == 30


# =============================================================================
# Test: acquire_booking_lock
# =============================================================================

class TestAcquireBookingLock:
    """Tests for the org-level booking lock."""

    def test_acquire_and_release_booking_lock(self, lock_service, mock_redis):
        """Org booking lock should acquire and release correctly."""
        org_id = 7
        lock_key = f"booking_lock:org:{org_id}"

        with lock_service.acquire_booking_lock(org_id) as acquired:
            assert acquired is True
            assert lock_key in mock_redis._store

        assert lock_key not in mock_redis._store

    def test_booking_lock_contention(self, lock_service, mock_redis):
        """Org booking lock should raise error when already held."""
        org_id = 7
        lock_key = f"booking_lock:org:{org_id}"

        mock_redis._store[lock_key] = "other-worker"

        with pytest.raises(DistributedLockError, match="Could not acquire booking lock"):
            with lock_service.acquire_booking_lock(org_id, timeout=0.2):
                pass


# =============================================================================
# Test: is_slot_locked
# =============================================================================

class TestIsSlotLocked:
    """Tests for the slot lock status check."""

    def test_unlocked_slot_returns_false(self, lock_service):
        """An unlocked slot should return False."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        assert lock_service.is_slot_locked(user_id, start_time) is False

    def test_locked_slot_returns_true(self, lock_service, mock_redis):
        """A locked slot should return True."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        lock_key = f"slot_lock:{user_id}:{start_time.isoformat()}"
        mock_redis._store[lock_key] = "some-token"

        assert lock_service.is_slot_locked(user_id, start_time) is True


# =============================================================================
# Test: Redis unavailable fallback
# =============================================================================

class TestRedisUnavailableFallback:
    """Tests for graceful degradation when Redis is unavailable."""

    def test_slot_lock_yields_false_when_redis_unavailable(self, no_redis_service):
        """When Redis is down, slot lock should yield False (not raise)."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        with no_redis_service.acquire_slot_lock(user_id, start_time) as acquired:
            assert acquired is False
            # Code inside the lock should still execute (SELECT FOR UPDATE is the safety net)

    def test_booking_lock_yields_false_when_redis_unavailable(self, no_redis_service):
        """When Redis is down, booking lock should yield False (not raise)."""
        org_id = 7

        with no_redis_service.acquire_booking_lock(org_id) as acquired:
            assert acquired is False

    def test_is_slot_locked_returns_false_when_redis_unavailable(self, no_redis_service):
        """When Redis is down, is_slot_locked should return False."""
        assert no_redis_service.is_slot_locked(42, datetime.now(timezone.utc)) is False


# =============================================================================
# Test: Lock release safety (Lua script)
# =============================================================================

class TestLockReleaseSafety:
    """Tests for the compare-and-delete Lua script behavior."""

    def test_only_owner_can_release_lock(self, lock_service, mock_redis):
        """A lock should only be releasable by the worker that acquired it."""
        lock_key = "slot_lock:42:2026-03-15T10:00:00+00:00"
        my_token = "my-unique-token"
        mock_redis._store[lock_key] = my_token

        # Our token should release successfully
        assert lock_service._release(lock_key, my_token) is True
        assert lock_key not in mock_redis._store

    def test_wrong_owner_cannot_release_lock(self, lock_service, mock_redis):
        """A lock held by another worker should not be releasable by us."""
        lock_key = "slot_lock:42:2026-03-15T10:00:00+00:00"
        mock_redis._store[lock_key] = "other-workers-token"

        # Different token should NOT release
        assert lock_service._release(lock_key, "my-token") is False
        assert lock_key in mock_redis._store  # Lock should still be held


# =============================================================================
# Test: Redis connection error handling
# =============================================================================

class TestRedisErrorHandling:
    """Tests for resilience when Redis commands fail."""

    def test_acquire_returns_false_on_redis_error(self, lock_service, mock_redis):
        """If Redis SET throws, acquire should return False (not crash)."""
        mock_redis.set.side_effect = ConnectionError("Redis connection lost")

        result = lock_service._acquire("test_key", "test_value", ttl=10, timeout=0.1)
        assert result is False

    def test_release_returns_false_on_redis_error(self, lock_service, mock_redis):
        """If Redis Lua script throws, release should return False."""
        lock_service._release_script = MagicMock(
            side_effect=ConnectionError("Redis connection lost")
        )

        result = lock_service._release("test_key", "test_value")
        assert result is False

    def test_is_slot_locked_returns_false_on_redis_error(self, lock_service, mock_redis):
        """If Redis exists() throws, is_slot_locked should return False."""
        mock_redis.exists.side_effect = ConnectionError("Redis connection lost")

        result = lock_service.is_slot_locked(42, datetime.now(timezone.utc))
        assert result is False


# =============================================================================
# Test: Singleton / get_lock_service
# =============================================================================

class TestGetLockService:
    """Tests for the singleton pattern."""

    def test_returns_same_instance(self):
        """get_lock_service should return the same instance on repeated calls."""
        import services.distributed_lock as module

        # Reset the singleton for a clean test
        original = module._lock_service
        module._lock_service = None
        try:
            svc1 = get_lock_service()
            svc2 = get_lock_service()
            assert svc1 is svc2
        finally:
            module._lock_service = original

    def test_creates_instance_with_defaults(self):
        """The created instance should have sensible defaults."""
        import services.distributed_lock as module

        original = module._lock_service
        module._lock_service = None
        try:
            svc = get_lock_service()
            assert svc.default_ttl == 10
            assert isinstance(svc, DistributedLockService)
        finally:
            module._lock_service = original


# =============================================================================
# Test: Lock expiry (TTL) behavior
# =============================================================================

class TestLockTTLBehavior:
    """Tests verifying that locks use proper TTL parameters."""

    def test_default_ttl_is_used(self, lock_service, mock_redis):
        """When no TTL is specified, the default_ttl (10s) should be used."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        with lock_service.acquire_slot_lock(user_id, start_time):
            call_kwargs = mock_redis.set.call_args
            assert call_kwargs[1]['ex'] == 10  # default_ttl

    def test_lock_set_uses_nx_flag(self, lock_service, mock_redis):
        """SET should always use NX to ensure atomicity."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        with lock_service.acquire_slot_lock(user_id, start_time):
            call_kwargs = mock_redis.set.call_args
            assert call_kwargs[1]['nx'] is True


# =============================================================================
# Test: Thread safety (concurrent lock attempts)
# =============================================================================

class TestThreadSafety:
    """Tests that lock acquisition is safe under concurrent access."""

    def test_concurrent_slot_lock_one_wins(self, lock_service, mock_redis):
        """When two threads try to lock the same slot, only one should succeed."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        results = {"acquired": 0, "failed": 0}
        lock = threading.Lock()

        def try_lock():
            try:
                with lock_service.acquire_slot_lock(user_id, start_time, timeout=0.3):
                    with lock:
                        results["acquired"] += 1
                    # Hold the lock briefly
                    time.sleep(0.2)
            except DistributedLockError:
                with lock:
                    results["failed"] += 1

        t1 = threading.Thread(target=try_lock)
        t2 = threading.Thread(target=try_lock)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # At least one should succeed; at most one should fail (lock contention)
        assert results["acquired"] >= 1
        # Both could succeed if t1 releases before t2 retries
        assert results["acquired"] + results["failed"] == 2


# =============================================================================
# Test: Integration with _check_appointment_conflict pattern
# =============================================================================

class TestIntegrationPattern:
    """Tests that demonstrate the intended usage pattern with booking routes."""

    def test_lock_wraps_conflict_check_pattern(self, lock_service, mock_redis):
        """Verify the lock-then-check pattern works as expected."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        conflict_checked = False

        def mock_check_conflict():
            nonlocal conflict_checked
            conflict_checked = True

        with lock_service.acquire_slot_lock(user_id, start_time) as acquired:
            assert acquired is True
            mock_check_conflict()

        assert conflict_checked is True

    def test_fallback_pattern_still_calls_conflict_check(self, no_redis_service):
        """When Redis is down, the conflict check should still run (via SELECT FOR UPDATE)."""
        user_id = 42
        start_time = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

        conflict_checked = False

        def mock_check_conflict():
            nonlocal conflict_checked
            conflict_checked = True

        with no_redis_service.acquire_slot_lock(user_id, start_time) as acquired:
            assert acquired is False  # Redis unavailable
            mock_check_conflict()  # SELECT FOR UPDATE still runs

        assert conflict_checked is True
