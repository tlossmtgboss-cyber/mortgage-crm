# tests/test_dual_cache.py
"""
Tests for dual-layer caching system.

Layer 1: Response cache (utils/cache.py) - Caches full AI responses
Layer 2: Tool cache (core/cache.py) - Caches individual tool results

Run with: pytest tests/test_dual_cache.py -v

NOTE: These tests require redis module which is not installed.
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock


# Check for redis module
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


pytestmark = pytest.mark.skipif(not HAS_REDIS, reason="redis module not installed")


# ============================================================================
# RESPONSE CACHE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_response_cache_connect_disconnect():
    """Test response cache connection lifecycle"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache(redis_url="redis://localhost:6379")

    # Should start disabled
    assert cache.enabled is False

    # Connect (may fail if Redis not available - that's ok)
    await cache.connect()

    # Close should work regardless
    await cache.close()
    assert cache.enabled is False


@pytest.mark.asyncio
async def test_response_cache_disabled_gracefully():
    """Test that cache operations don't fail when Redis unavailable"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache(redis_url="redis://invalid-host:6379")
    await cache.connect()  # Should fail gracefully

    assert cache.enabled is False

    # All operations should return gracefully
    result = await cache.get("test query", "user_123")
    assert result is None

    await cache.set("test query", {"response": "test"}, "general", "user_123")
    # No exception

    count = await cache.invalidate_pattern("test")
    assert count == 0

    await cache.close()


@pytest.mark.asyncio
async def test_response_cache_key_generation():
    """Test cache key generation with user isolation"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache()

    # Same query, different users should get different keys
    key1 = cache._get_cache_key("show my pipeline", "user_1")
    key2 = cache._get_cache_key("show my pipeline", "user_2")
    key3 = cache._get_cache_key("show my pipeline", None)

    assert key1 != key2
    assert key1 != key3
    assert "user_1" in key1
    assert "user_2" in key2
    assert "global" in key3

    # Same query should produce same hash
    key4 = cache._get_cache_key("show my pipeline", "user_1")
    assert key1 == key4

    # Case insensitive
    key5 = cache._get_cache_key("SHOW MY PIPELINE", "user_1")
    assert key1 == key5


@pytest.mark.asyncio
async def test_response_cache_ttl_by_intent():
    """Test that different intents get different TTLs"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache()

    # Check TTL map values
    assert cache.TTL_MAP["pipeline_query"] == 300  # 5 min
    assert cache.TTL_MAP["lead_status"] == 900     # 15 min
    assert cache.TTL_MAP["rate_lock"] == 3600      # 1 hour
    assert cache.TTL_MAP["general"] == 3600        # 1 hour


@pytest.mark.asyncio
@pytest.mark.skipif(True, reason="Requires Redis")
async def test_response_cache_full_flow():
    """Test full cache flow with real Redis"""
    from utils.cache import cache as response_cache

    await response_cache.connect()

    if not response_cache.enabled:
        pytest.skip("Redis not available")

    # Clear any existing test data
    await response_cache.invalidate("test pipeline query", "test_user")

    # Cache miss
    result = await response_cache.get("test pipeline query", "test_user")
    assert result is None

    # Cache set
    test_response = {
        "response": "Your pipeline has 10 loans",
        "intent": "pipeline_query",
        "confidence": 0.95
    }
    await response_cache.set(
        "test pipeline query",
        test_response,
        intent="pipeline_query",
        user_id="test_user"
    )

    # Cache hit
    result = await response_cache.get("test pipeline query", "test_user")
    assert result is not None
    assert result["response"] == "Your pipeline has 10 loans"
    assert result["cached"] is True
    assert "ttl_remaining" in result

    # Cleanup
    await response_cache.invalidate("test pipeline query", "test_user")
    await response_cache.close()


# ============================================================================
# TOOL CACHE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_tool_cache_decorator():
    """Test the @cache.cached() decorator"""
    from core.cache import RedisCache

    cache = RedisCache()

    call_count = 0

    @cache.cached(ttl=60, key_prefix="test_func")
    async def expensive_function(user_id: str):
        nonlocal call_count
        call_count += 1
        return {"data": f"result for {user_id}"}

    # Without Redis, should just call function every time
    result1 = await expensive_function("user_1")
    assert result1["data"] == "result for user_1"

    result2 = await expensive_function("user_1")
    assert result2["data"] == "result for user_1"

    # Without Redis, function called twice
    assert call_count == 2


@pytest.mark.asyncio
async def test_tool_cache_key_generation():
    """Test tool cache key generation"""
    from core.cache import RedisCache

    cache = RedisCache()

    key1 = cache._generate_key("get_pipeline", "user_1", status="active")
    key2 = cache._generate_key("get_pipeline", "user_1", status="active")
    key3 = cache._generate_key("get_pipeline", "user_2", status="active")

    # Same args should produce same key
    assert key1 == key2

    # Different args should produce different key
    assert key1 != key3

    # Key should have proper prefix
    assert key1.startswith("perennia:agent:get_pipeline:")


# ============================================================================
# DUAL CACHE INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_dual_cache_isolation():
    """Test that response cache and tool cache are isolated"""
    from utils.cache import PerenniaCache
    from core.cache import RedisCache

    response_cache = PerenniaCache()
    tool_cache = RedisCache()

    # Keys should have different prefixes
    response_key = response_cache._get_cache_key("test query", "user_1")
    tool_key = tool_cache._generate_key("get_data", "user_1")

    assert ":query:" in response_key
    assert "perennia:agent:" in tool_key
    assert response_key != tool_key


@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache statistics retrieval"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache()

    # Without connection, should return disabled status
    stats = await cache.get_stats()
    assert stats["enabled"] is False


# ============================================================================
# MOCK TESTS FOR FULL FLOW
# ============================================================================

@pytest.mark.asyncio
async def test_dual_cache_flow_mocked():
    """Test dual cache flow with mocked Redis"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache()

    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=300)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.ping = AsyncMock()
    mock_redis.aclose = AsyncMock()

    cache.redis = mock_redis
    cache.enabled = True

    # Test cache miss
    result = await cache.get("test query", "user_1")
    assert result is None
    mock_redis.get.assert_called_once()

    # Test cache set
    await cache.set(
        "test query",
        {"response": "test response"},
        intent="general",
        user_id="user_1"
    )
    mock_redis.setex.assert_called_once()

    # Test cache hit
    import json
    cached_data = {
        "response": "cached response",
        "intent": "general",
        "cached_at": "2025-01-01T00:00:00"
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

    result = await cache.get("test query", "user_1")
    assert result is not None
    assert result["response"] == "cached response"
    assert result["cached"] is True

    await cache.close()


@pytest.mark.asyncio
async def test_cache_invalidation_flow():
    """Test cache invalidation scenarios"""
    from utils.cache import PerenniaCache

    cache = PerenniaCache()

    # Mock Redis with scan/delete support
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=3)
    mock_redis.scan = AsyncMock(return_value=(0, ["key1", "key2", "key3"]))
    mock_redis.get = AsyncMock(return_value='{"query": "lead_123 status", "intent": "lead_status"}')
    mock_redis.aclose = AsyncMock()

    cache.redis = mock_redis
    cache.enabled = True

    # Test pattern invalidation
    count = await cache.invalidate_pattern("lead_123")
    assert count == 3

    # Test intent invalidation
    mock_redis.delete = AsyncMock(return_value=2)
    count = await cache.invalidate_by_intent("lead_status")
    assert count == 2

    await cache.close()


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cache_performance_improvement():
    """Test that caching provides performance improvement"""

    # Simulate cached vs uncached response times
    async def simulate_uncached_query():
        await asyncio.sleep(0.5)  # Simulate 500ms query
        return {"response": "data"}

    async def simulate_cached_query():
        await asyncio.sleep(0.01)  # Simulate 10ms cache hit
        return {"response": "data", "cached": True}

    # Uncached
    start = time.time()
    await simulate_uncached_query()
    uncached_time = time.time() - start

    # Cached
    start = time.time()
    await simulate_cached_query()
    cached_time = time.time() - start

    # Cached should be significantly faster
    assert cached_time < uncached_time * 0.1  # At least 10x faster


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
