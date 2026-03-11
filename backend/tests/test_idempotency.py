"""
Tests for Idempotency Middleware

Validates that:
- First request executes handler and caches response
- Second request with same key returns cached response
- Different keys execute independently
- Expired keys re-execute
- Missing header skips idempotency
- Redis failure degrades gracefully (requests still processed)
- Non-matching paths and GET requests are unaffected
- Concurrent duplicate requests are handled via locking
"""

import json
import time
import uuid
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from middleware.idempotency import (
    CachedResponse,
    IdempotencyMiddleware,
    IdempotencyStore,
    IDEMPOTENCY_HEADER,
    MAX_KEY_LENGTH,
)


# =============================================================================
# IN-MEMORY STORE FOR TESTING (no Redis required)
# =============================================================================

class InMemoryIdempotencyStore(IdempotencyStore):
    """
    In-memory implementation of IdempotencyStore for testing.
    No Redis dependency required.
    """

    def __init__(self, ttl_seconds: int = 300):
        # Skip parent __init__ (which tries to connect to Redis)
        self._redis = None
        self._available_flag = True
        self._store: dict = {}  # key -> (CachedResponse, expire_time)
        self._locks: dict = {}  # key -> expire_time
        self._default_ttl = ttl_seconds

    @property
    def available(self) -> bool:
        return self._available_flag

    @available.setter
    def available(self, value: bool):
        self._available_flag = value

    def _cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        self._store = {
            k: v for k, v in self._store.items() if v[1] > now
        }
        self._locks = {
            k: v for k, v in self._locks.items() if v > now
        }

    async def get(self, key: str):
        if not self.available:
            return None
        self._cleanup_expired()
        entry = self._store.get(f"idempotency:response:{key}")
        if entry is None:
            return None
        return entry[0]

    async def set(self, key: str, response: CachedResponse, ttl: int = 300):
        if not self.available:
            return False
        expire_at = time.time() + ttl
        self._store[f"idempotency:response:{key}"] = (response, expire_at)
        return True

    async def exists(self, key: str):
        if not self.available:
            return False
        self._cleanup_expired()
        return f"idempotency:response:{key}" in self._store

    async def acquire_lock(self, key: str):
        if not self.available:
            return True  # Fail open
        self._cleanup_expired()
        lock_key = f"idempotency:lock:{key}"
        if lock_key in self._locks:
            return False
        self._locks[lock_key] = time.time() + 30
        return True

    async def release_lock(self, key: str):
        if not self.available:
            return
        lock_key = f"idempotency:lock:{key}"
        self._locks.pop(lock_key, None)

    def expire_key(self, key: str):
        """Test helper: force-expire a cached response."""
        full_key = f"idempotency:response:{key}"
        if full_key in self._store:
            cached, _ = self._store[full_key]
            self._store[full_key] = (cached, time.time() - 1)

    def clear(self):
        """Test helper: clear all entries."""
        self._store.clear()
        self._locks.clear()


# =============================================================================
# FIXTURES
# =============================================================================

def _find_idempotency_middleware(app) -> IdempotencyMiddleware:
    """Walk Starlette middleware stack to find our IdempotencyMiddleware."""
    current = getattr(app, "middleware_stack", app)
    while current is not None:
        if isinstance(current, IdempotencyMiddleware):
            return current
        current = getattr(current, "app", None)
    return None


def create_test_app(memory_store: InMemoryIdempotencyStore):
    """
    Create a minimal Starlette app with IdempotencyMiddleware for testing.

    Endpoints:
    - POST /api/v1/vapi/webhook -> JSON with unique request_id
    - POST /api/v1/scheduler/appointments -> appointment created (201)
    - GET /api/v1/vapi/status -> status ok (GET, not idempotent)
    - POST /api/other/endpoint -> not in idempotent paths
    """
    call_count = {"webhook": 0, "appointment": 0}

    async def webhook_handler(request: Request) -> JSONResponse:
        call_count["webhook"] += 1
        return JSONResponse(
            status_code=200,
            content={
                "status": "received",
                "request_id": str(uuid.uuid4()),
                "call_count": call_count["webhook"],
            },
        )

    async def appointment_handler(request: Request) -> JSONResponse:
        call_count["appointment"] += 1
        return JSONResponse(
            status_code=201,
            content={
                "id": call_count["appointment"],
                "status": "created",
                "call_count": call_count["appointment"],
            },
        )

    async def status_handler(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={"status": "ok"},
        )

    async def other_handler(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={"result": "processed"},
        )

    routes = [
        Route("/api/v1/vapi/webhook", webhook_handler, methods=["POST"]),
        Route(
            "/api/v1/scheduler/appointments",
            appointment_handler,
            methods=["POST"],
        ),
        Route("/api/v1/vapi/status", status_handler, methods=["GET"]),
        Route("/api/other/endpoint", other_handler, methods=["POST"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        IdempotencyMiddleware,
        redis_url="",  # Won't connect - we'll replace the store
        ttl_seconds=300,
        paths=["/api/v1/vapi/", "/api/v1/scheduler/appointments"],
    )

    client = TestClient(app, raise_server_exceptions=False)

    # Starlette builds the middleware stack lazily on the first request.
    # Send a dummy request to trigger the build, then swap the store.
    client.get("/api/v1/vapi/status")

    middleware = _find_idempotency_middleware(app)
    if middleware:
        middleware.store = memory_store

    return client, call_count


@pytest.fixture
def memory_store():
    """Create an in-memory idempotency store."""
    return InMemoryIdempotencyStore()


@pytest.fixture
def test_app(memory_store):
    """Create a test app with in-memory store."""
    client, call_count = create_test_app(memory_store)
    return client, call_count, memory_store


# =============================================================================
# CACHED RESPONSE MODEL TESTS
# =============================================================================

class TestCachedResponse:
    """Tests for CachedResponse serialization."""

    def test_round_trip_serialization(self):
        """CachedResponse survives JSON round-trip."""
        original = CachedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"status": "ok"}',
        )

        json_str = original.to_json()
        restored = CachedResponse.from_json(json_str)

        assert restored.status_code == original.status_code
        assert restored.headers == original.headers
        assert restored.body == original.body

    def test_to_starlette_response(self):
        """CachedResponse converts to a valid Starlette Response."""
        cached = CachedResponse(
            status_code=201,
            headers={"content-type": "application/json", "x-custom": "value"},
            body=b'{"id": 42}',
        )

        response = cached.to_starlette_response()
        assert response.status_code == 201
        assert response.body == b'{"id": 42}'

    def test_empty_body(self):
        """CachedResponse handles empty body."""
        cached = CachedResponse(
            status_code=204,
            headers={},
            body=b"",
        )
        json_str = cached.to_json()
        restored = CachedResponse.from_json(json_str)
        assert restored.body == b""
        assert restored.status_code == 204


# =============================================================================
# IN-MEMORY STORE TESTS
# =============================================================================

class TestInMemoryStore:
    """Tests for the in-memory store implementation."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, memory_store):
        cached = CachedResponse(200, {"content-type": "application/json"}, b"test")
        await memory_store.set("key1", cached, ttl=60)

        result = await memory_store.get("key1")
        assert result is not None
        assert result.status_code == 200
        assert result.body == b"test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, memory_store):
        result = await memory_store.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, memory_store):
        cached = CachedResponse(200, {}, b"")
        await memory_store.set("key1", cached)

        assert await memory_store.exists("key1") is True
        assert await memory_store.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_expired_key_returns_none(self, memory_store):
        cached = CachedResponse(200, {}, b"data")
        await memory_store.set("key1", cached, ttl=1)

        # Force expiry
        memory_store.expire_key("key1")

        result = await memory_store.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_lock_acquire_and_release(self, memory_store):
        assert await memory_store.acquire_lock("key1") is True
        # Second acquire should fail
        assert await memory_store.acquire_lock("key1") is False
        # Release and re-acquire
        await memory_store.release_lock("key1")
        assert await memory_store.acquire_lock("key1") is True

    @pytest.mark.asyncio
    async def test_unavailable_store_returns_none(self, memory_store):
        memory_store.available = False
        cached = CachedResponse(200, {}, b"")
        assert await memory_store.get("key1") is None
        assert await memory_store.set("key1", cached) is False
        assert await memory_store.exists("key1") is False
        # Lock should fail open (return True)
        assert await memory_store.acquire_lock("key1") is True


# =============================================================================
# MIDDLEWARE INTEGRATION TESTS
# =============================================================================

class TestIdempotencyMiddleware:
    """Integration tests for IdempotencyMiddleware."""

    def test_first_request_executes_and_caches(self, test_app):
        """First request with idempotency key should execute the handler and cache."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        response = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["call_count"] == 1
        # Should indicate key was accepted
        assert response.headers.get("X-Idempotency-Key-Accepted") == "true"
        # Handler was called exactly once
        assert call_count["webhook"] == 1

    def test_second_request_returns_cached_response(self, test_app):
        """Second request with the same key returns cached response without re-executing."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        # First request
        response1 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )
        assert response1.status_code == 200
        first_request_id = response1.json()["request_id"]

        # Second request with same key
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )

        assert response2.status_code == 200
        # Should be the same cached response
        assert response2.json()["request_id"] == first_request_id
        assert response2.json()["call_count"] == 1
        # Should indicate this is a replay
        assert response2.headers.get("X-Idempotency-Replay") == "true"
        # Handler should NOT have been called again
        assert call_count["webhook"] == 1

    def test_different_keys_execute_independently(self, test_app):
        """Different idempotency keys should execute independently."""
        client, call_count, store = test_app
        key1 = str(uuid.uuid4())
        key2 = str(uuid.uuid4())

        response1 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key1},
            json={"message": {"type": "call-started"}},
        )
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key2},
            json={"message": {"type": "call-started"}},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Different request IDs (executed separately)
        assert response1.json()["request_id"] != response2.json()["request_id"]
        # Handler called twice
        assert call_count["webhook"] == 2

    def test_expired_key_re_executes(self, test_app):
        """After a key expires, the same key should re-execute the handler."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        # First request
        response1 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )
        assert call_count["webhook"] == 1
        first_request_id = response1.json()["request_id"]

        # Expire the cached response
        store.expire_key(key)

        # Second request with same key after expiry
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )

        assert response2.status_code == 200
        # Should be a new execution (different request_id)
        assert response2.json()["request_id"] != first_request_id
        assert response2.json()["call_count"] == 2
        # Handler called twice total
        assert call_count["webhook"] == 2

    def test_missing_header_skips_idempotency(self, test_app):
        """Requests without X-Idempotency-Key should execute normally every time."""
        client, call_count, store = test_app

        response1 = client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "call-started"}},
        )
        response2 = client.post(
            "/api/v1/vapi/webhook",
            json={"message": {"type": "call-started"}},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Handler called twice (no caching)
        assert call_count["webhook"] == 2
        # No idempotency headers in response
        assert "X-Idempotency-Key-Accepted" not in response1.headers
        assert "X-Idempotency-Replay" not in response1.headers

    def test_redis_failure_degrades_gracefully(self, test_app):
        """If Redis is unavailable, requests should still be processed."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        # Simulate Redis going down
        store.available = False

        response = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "received"
        # Handler was called (no caching, no blocking)
        assert call_count["webhook"] == 1

        # Second request also goes through (no caching)
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )
        assert response2.status_code == 200
        assert call_count["webhook"] == 2

    def test_get_request_skips_idempotency(self, test_app):
        """GET requests should bypass idempotency even on matching paths."""
        client, call_count, store = test_app

        response = client.get(
            "/api/v1/vapi/status",
            headers={IDEMPOTENCY_HEADER: str(uuid.uuid4())},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_non_matching_path_skips_idempotency(self, test_app):
        """POST to non-matching paths should bypass idempotency."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        response1 = client.post(
            "/api/other/endpoint",
            headers={IDEMPOTENCY_HEADER: key},
            json={"data": "test"},
        )
        response2 = client.post(
            "/api/other/endpoint",
            headers={IDEMPOTENCY_HEADER: key},
            json={"data": "test"},
        )

        # Both should execute (not cached)
        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_scheduler_appointments_path(self, test_app):
        """Scheduler appointments path should be covered by idempotency."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        response1 = client.post(
            "/api/v1/scheduler/appointments",
            headers={IDEMPOTENCY_HEADER: key},
            json={"time": "10:00", "date": "2026-03-15"},
        )
        response2 = client.post(
            "/api/v1/scheduler/appointments",
            headers={IDEMPOTENCY_HEADER: key},
            json={"time": "10:00", "date": "2026-03-15"},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        # Same cached response
        assert response1.json()["id"] == response2.json()["id"]
        # Handler called once
        assert call_count["appointment"] == 1
        # Second response is a replay
        assert response2.headers.get("X-Idempotency-Replay") == "true"

    def test_key_too_long_skips_idempotency(self, test_app):
        """Keys longer than MAX_KEY_LENGTH should be ignored."""
        client, call_count, store = test_app
        long_key = "x" * (MAX_KEY_LENGTH + 1)

        response1 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: long_key},
            json={"message": {"type": "call-started"}},
        )
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: long_key},
            json={"message": {"type": "call-started"}},
        )

        # Both execute (key was ignored)
        assert call_count["webhook"] == 2

    def test_empty_key_skips_idempotency(self, test_app):
        """Empty or whitespace-only keys should be ignored."""
        client, call_count, store = test_app

        response = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: "   "},
            json={"message": {"type": "call-started"}},
        )
        assert response.status_code == 200
        assert call_count["webhook"] == 1

        # Another request - also executes
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: "   "},
            json={"message": {"type": "call-started"}},
        )
        assert call_count["webhook"] == 2

    def test_redis_goes_down_mid_operation(self, test_app):
        """If Redis goes down between check and store, request still completes."""
        client, call_count, store = test_app
        key = str(uuid.uuid4())

        # First request succeeds with Redis available
        response1 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key},
            json={"message": {"type": "call-started"}},
        )
        assert response1.status_code == 200
        assert call_count["webhook"] == 1

        # Redis goes down
        store.available = False

        # New key request still works
        key2 = str(uuid.uuid4())
        response2 = client.post(
            "/api/v1/vapi/webhook",
            headers={IDEMPOTENCY_HEADER: key2},
            json={"message": {"type": "call-started"}},
        )
        assert response2.status_code == 200
        assert call_count["webhook"] == 2


# =============================================================================
# IDEMPOTENCY STORE UNIT TESTS (Redis mock)
# =============================================================================

class TestIdempotencyStoreInit:
    """Tests for IdempotencyStore initialization."""

    def test_no_redis_url_disables_store(self):
        """Store is disabled when no REDIS_URL is set."""
        import os
        orig = os.environ.pop("REDIS_URL", None)
        try:
            store = IdempotencyStore(redis_url="")
            assert store.available is False
        finally:
            if orig is not None:
                os.environ["REDIS_URL"] = orig

    def test_redis_connection_failure_disables_store(self):
        """Store is disabled when Redis connection fails."""
        store = IdempotencyStore(redis_url="redis://nonexistent-host:9999/0")
        assert store.available is False

    @pytest.mark.asyncio
    async def test_unavailable_store_methods_fail_gracefully(self):
        """All methods return safe defaults when store is unavailable."""
        store = IdempotencyStore(redis_url="")
        cached = CachedResponse(200, {}, b"test")

        assert await store.get("key") is None
        assert await store.set("key", cached) is False
        assert await store.exists("key") is False
        assert await store.acquire_lock("key") is True  # Fail open
        await store.release_lock("key")  # No-op, should not raise


# =============================================================================
# MIDDLEWARE EDGE CASE TESTS
# =============================================================================

class TestIdempotencyEdgeCases:
    """Edge case tests for the middleware."""

    def test_triple_retry_same_key(self, test_app):
        """Simulate Vapi's 3x retry pattern - all should get same response."""
        client, call_count, store = test_app
        key = f"vapi-retry-{uuid.uuid4()}"

        responses = []
        for i in range(3):
            resp = client.post(
                "/api/v1/vapi/webhook",
                headers={IDEMPOTENCY_HEADER: key},
                json={"message": {"type": "end-of-call-report"}},
            )
            responses.append(resp)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # All should have the same request_id
        request_ids = [r.json()["request_id"] for r in responses]
        assert len(set(request_ids)) == 1, "All retries should get same response"

        # Handler should only have been called once
        assert call_count["webhook"] == 1

        # First response should have accepted header
        assert responses[0].headers.get("X-Idempotency-Key-Accepted") == "true"
        # Subsequent responses should have replay header
        assert responses[1].headers.get("X-Idempotency-Replay") == "true"
        assert responses[2].headers.get("X-Idempotency-Replay") == "true"

    def test_interleaved_keys(self, test_app):
        """Multiple different keys interleaved should each be independent."""
        client, call_count, store = test_app
        keys = [str(uuid.uuid4()) for _ in range(5)]

        # Send first request for each key
        first_responses = {}
        for key in keys:
            resp = client.post(
                "/api/v1/vapi/webhook",
                headers={IDEMPOTENCY_HEADER: key},
                json={"message": {"type": "call-started"}},
            )
            first_responses[key] = resp.json()

        assert call_count["webhook"] == 5

        # Retry each key
        for key in keys:
            resp = client.post(
                "/api/v1/vapi/webhook",
                headers={IDEMPOTENCY_HEADER: key},
                json={"message": {"type": "call-started"}},
            )
            # Should match the first response for this key
            assert resp.json()["request_id"] == first_responses[key]["request_id"]

        # No additional handler calls
        assert call_count["webhook"] == 5
