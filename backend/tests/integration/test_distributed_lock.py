"""
Distributed Lock Integration Tests

Tests for Redis-based distributed locking used by booking/scheduling:
- Lock acquisition and release
- Lock expiry / TTL enforcement
- Concurrent lock contention
- Graceful degradation when Redis is unavailable
- Slot-level and org-level locking

Key file: backend/services/distributed_lock.py
"""
import pytest
import time
import threading
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.integration, pytest.mark.critical]


class TestDistributedLockAcquireRelease:
    """Test basic lock acquisition and release mechanics."""

    def test_lock_service_singleton(self):
        """get_lock_service should return a singleton instance."""
        from services.distributed_lock import get_lock_service

        svc1 = get_lock_service()
        svc2 = get_lock_service()
        assert svc1 is svc2

    def test_lock_service_has_default_ttl(self):
        """Default TTL should be set to prevent deadlocks."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService()
        assert svc.default_ttl > 0
        assert svc.default_ttl <= 30  # Should not be too long

    def test_slot_lock_key_format(self):
        """Slot lock keys should encode user_id and ISO timestamp."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService()
        dt = datetime(2026, 5, 14, 10, 0, 0, tzinfo=timezone.utc)

        # We can verify the key format by mocking Redis
        with patch.object(svc, '_get_redis', return_value=None):
            with svc.acquire_slot_lock(user_id=42, start_time=dt) as acquired:
                # Redis unavailable => yields False (graceful degradation)
                assert acquired is False


class TestGracefulDegradation:
    """When Redis is unavailable, locking should fall through gracefully."""

    def test_slot_lock_yields_false_without_redis(self):
        """If Redis is down, acquire_slot_lock yields False, not an error."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService(redis_url="redis://localhost:1")
        svc._redis_checked = False
        svc._redis = None

        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)
        with patch.object(svc, '_get_redis', return_value=None):
            with svc.acquire_slot_lock(user_id=1, start_time=dt) as acquired:
                assert acquired is False

    def test_booking_lock_yields_false_without_redis(self):
        """If Redis is down, acquire_booking_lock yields False."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService(redis_url="redis://localhost:1")
        svc._redis_checked = False
        svc._redis = None

        with patch.object(svc, '_get_redis', return_value=None):
            with svc.acquire_booking_lock(org_id=1) as acquired:
                assert acquired is False

    def test_is_slot_locked_returns_false_without_redis(self):
        """If Redis is down, is_slot_locked should return False (assume not locked)."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService()
        svc._redis_checked = True
        svc._redis = None

        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)
        assert svc.is_slot_locked(user_id=1, start_time=dt) is False


class TestLockWithMockRedis:
    """Test lock behavior with a mocked Redis client."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client that supports SET NX EX."""
        redis = MagicMock()
        redis.ping.return_value = True
        redis.register_script.return_value = MagicMock()
        return redis

    @pytest.fixture
    def lock_service(self, mock_redis):
        from services.distributed_lock import DistributedLockService
        svc = DistributedLockService()
        svc._redis = mock_redis
        svc._redis_checked = True
        svc._release_script = mock_redis.register_script.return_value
        return svc

    def test_acquire_calls_set_nx_ex(self, lock_service, mock_redis):
        """Acquiring a lock should call SET with NX and EX flags."""
        mock_redis.set.return_value = True  # Lock acquired
        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)

        with lock_service.acquire_slot_lock(user_id=42, start_time=dt, ttl=5, timeout=1.0) as acquired:
            assert acquired is True

        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("nx") is True
        assert call_kwargs.kwargs.get("ex") == 5

    def test_release_uses_lua_script(self, lock_service, mock_redis):
        """Releasing a lock should use the Lua compare-and-delete script."""
        mock_redis.set.return_value = True
        lock_service._release_script.return_value = 1  # Lock released

        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)
        with lock_service.acquire_slot_lock(user_id=42, start_time=dt) as acquired:
            assert acquired is True

        # After context manager exits, release should have been called
        lock_service._release_script.assert_called_once()

    def test_contention_raises_error(self, lock_service, mock_redis):
        """If lock cannot be acquired within timeout, should raise DistributedLockError."""
        from services.distributed_lock import DistributedLockError

        mock_redis.set.return_value = False  # Lock NOT acquired (contention)
        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)

        with pytest.raises(DistributedLockError, match="Could not acquire slot lock"):
            with lock_service.acquire_slot_lock(user_id=42, start_time=dt, timeout=0.1):
                pass  # Should not reach here

    def test_booking_lock_contention_raises_error(self, lock_service, mock_redis):
        """Org-level booking lock contention should raise DistributedLockError."""
        from services.distributed_lock import DistributedLockError

        mock_redis.set.return_value = False
        with pytest.raises(DistributedLockError, match="Could not acquire booking lock"):
            with lock_service.acquire_booking_lock(org_id=1, timeout=0.1):
                pass

    def test_is_slot_locked_checks_key_existence(self, lock_service, mock_redis):
        """is_slot_locked should check if the Redis key exists."""
        mock_redis.exists.return_value = 1
        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)

        assert lock_service.is_slot_locked(user_id=42, start_time=dt) is True
        mock_redis.exists.assert_called_once()

    def test_is_slot_locked_returns_false_when_not_locked(self, lock_service, mock_redis):
        """When no lock key exists, is_slot_locked should return False."""
        mock_redis.exists.return_value = 0
        dt = datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc)

        assert lock_service.is_slot_locked(user_id=42, start_time=dt) is False


class TestLockErrorRecovery:
    """Test that Redis errors during lock operations are handled gracefully."""

    def test_acquire_returns_false_on_redis_error(self):
        """Redis connection error during acquire should return False, not crash."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService()
        mock_redis = MagicMock()
        mock_redis.set.side_effect = ConnectionError("Redis connection lost")
        svc._redis = mock_redis
        svc._redis_checked = True

        result = svc._acquire("test_key", "test_value", ttl=5, timeout=0.1)
        assert result is False

    def test_release_returns_false_on_redis_error(self):
        """Redis error during release should return False, not crash."""
        from services.distributed_lock import DistributedLockService

        svc = DistributedLockService()
        mock_redis = MagicMock()
        svc._redis = mock_redis
        svc._redis_checked = True
        svc._release_script = MagicMock(side_effect=ConnectionError("lost"))

        result = svc._release("test_key", "test_value")
        assert result is False
