"""
Idempotency Middleware for Webhook Endpoints

Prevents duplicate operations when webhook providers (e.g., Vapi) retry
requests on timeout. Caches responses by X-Idempotency-Key header so that
retried requests return the original response without re-executing the handler.

How it works:
    1. Client sends request with X-Idempotency-Key header.
    2. Middleware checks Redis for a cached response under that key.
    3. If found: return cached response immediately (no handler execution).
    4. If not found: execute handler, cache the response, return it.
    5. Keys expire after a configurable TTL (default 5 minutes).
    6. Requests without the header bypass idempotency entirely.

Graceful degradation:
    If Redis is unavailable, the middleware logs a warning and allows the
    request through without idempotency protection. This ensures webhook
    endpoints never fail due to a Redis outage.

Usage in main.py:
    from middleware.idempotency import IdempotencyMiddleware
    app.add_middleware(
        IdempotencyMiddleware,
        redis_url=os.getenv("REDIS_URL"),
        ttl_seconds=300,
        paths=["/api/v1/vapi/", "/api/v1/scheduler/appointments"],
    )
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Header name for the idempotency key
IDEMPOTENCY_HEADER = "X-Idempotency-Key"

# HTTP methods that support idempotency (only mutating methods)
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}

# Maximum allowed key length to prevent abuse
MAX_KEY_LENGTH = 256


# =============================================================================
# CACHED RESPONSE MODEL
# =============================================================================

@dataclass
class CachedResponse:
    """Serializable representation of an HTTP response for cache storage."""
    status_code: int
    headers: Dict[str, str]
    body: bytes

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps({
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body.decode("utf-8", errors="replace"),
        })

    @classmethod
    def from_json(cls, data: str) -> "CachedResponse":
        """Deserialize from JSON stored in Redis."""
        parsed = json.loads(data)
        return cls(
            status_code=parsed["status_code"],
            headers=parsed["headers"],
            body=parsed["body"].encode("utf-8"),
        )

    def to_starlette_response(self) -> Response:
        """Convert back to a Starlette Response."""
        return Response(
            content=self.body,
            status_code=self.status_code,
            headers=self.headers,
        )


# =============================================================================
# IDEMPOTENCY STORE
# =============================================================================

class IdempotencyStore:
    """
    Redis-backed store for idempotency keys and cached responses.

    Uses Redis SET with NX (set-if-not-exists) for atomic lock acquisition,
    ensuring that concurrent duplicate requests don't both execute.

    Key layout in Redis:
        idempotency:response:{key}  -> JSON-serialized CachedResponse
        idempotency:lock:{key}      -> "processing" (short-lived lock)
    """

    RESPONSE_PREFIX = "idempotency:response:"
    LOCK_PREFIX = "idempotency:lock:"
    # Lock TTL should be long enough for the slowest webhook handler
    LOCK_TTL_SECONDS = 30

    def __init__(self, redis_url: Optional[str] = None):
        self._redis: Any = None
        self._available = False
        self._redis_url = redis_url or os.getenv("REDIS_URL", "")
        self._connect()

    def _connect(self):
        """Attempt to connect to Redis. Fail silently if unavailable."""
        if not self._redis_url:
            logger.warning(
                "IdempotencyStore: No REDIS_URL configured - "
                "idempotency caching disabled"
            )
            return

        try:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True,
            )
            # Verify connectivity
            self._redis.ping()
            self._available = True
            logger.info("IdempotencyStore: Connected to Redis")
        except Exception as e:
            logger.warning(
                "IdempotencyStore: Redis unavailable (%s) - "
                "idempotency caching disabled",
                e,
            )
            self._redis = None
            self._available = False

    @property
    def available(self) -> bool:
        """Check if the store is available for use."""
        return self._available and self._redis is not None

    async def get(self, key: str) -> Optional[CachedResponse]:
        """
        Retrieve a cached response by idempotency key.

        Returns None if not found or Redis is unavailable.
        """
        if not self.available:
            return None

        try:
            response_key = f"{self.RESPONSE_PREFIX}{key}"
            data = self._redis.get(response_key)
            if data is None:
                return None
            return CachedResponse.from_json(data)
        except Exception as e:
            logger.warning("IdempotencyStore.get failed: %s", e)
            return None

    async def set(
        self, key: str, response: CachedResponse, ttl: int = 300
    ) -> bool:
        """
        Store a cached response with the given TTL.

        Returns True if stored successfully, False otherwise.
        """
        if not self.available:
            return False

        try:
            response_key = f"{self.RESPONSE_PREFIX}{key}"
            self._redis.setex(response_key, ttl, response.to_json())
            return True
        except Exception as e:
            logger.warning("IdempotencyStore.set failed: %s", e)
            return False

    async def exists(self, key: str) -> bool:
        """Check if an idempotency key has a cached response."""
        if not self.available:
            return False

        try:
            response_key = f"{self.RESPONSE_PREFIX}{key}"
            return bool(self._redis.exists(response_key))
        except Exception as e:
            logger.warning("IdempotencyStore.exists failed: %s", e)
            return False

    async def acquire_lock(self, key: str) -> bool:
        """
        Acquire a processing lock for the given key.

        Uses SET NX (set-if-not-exists) for atomic lock acquisition.
        Returns True if lock acquired (this request should process),
        False if another request is already processing this key.
        """
        if not self.available:
            # If Redis is down, allow processing (fail open)
            return True

        try:
            lock_key = f"{self.LOCK_PREFIX}{key}"
            acquired = self._redis.set(
                lock_key,
                "processing",
                nx=True,
                ex=self.LOCK_TTL_SECONDS,
            )
            return bool(acquired)
        except Exception as e:
            logger.warning("IdempotencyStore.acquire_lock failed: %s", e)
            return True  # Fail open

    async def release_lock(self, key: str):
        """Release the processing lock for the given key."""
        if not self.available:
            return

        try:
            lock_key = f"{self.LOCK_PREFIX}{key}"
            self._redis.delete(lock_key)
        except Exception as e:
            logger.warning("IdempotencyStore.release_lock failed: %s", e)


# =============================================================================
# IDEMPOTENCY MIDDLEWARE
# =============================================================================

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that caches responses by X-Idempotency-Key header
    to prevent duplicate webhook operations.

    Only applies to POST/PUT/PATCH requests on configured path prefixes.
    Requests without the header or on non-matching paths pass through
    unchanged.

    Args:
        app: The ASGI application.
        redis_url: Redis connection URL. Falls back to REDIS_URL env var.
        ttl_seconds: How long to cache responses (default 300 = 5 minutes).
        paths: List of URL path prefixes to apply idempotency to.
    """

    def __init__(
        self,
        app,
        redis_url: Optional[str] = None,
        ttl_seconds: int = 300,
        paths: Optional[List[str]] = None,
    ):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
        self.paths = paths or [
            "/api/v1/vapi/",
            "/api/vapi/",
            "/api/v1/scheduler/appointments",
        ]
        self.store = IdempotencyStore(redis_url=redis_url)

    def _should_apply(self, request: Request) -> bool:
        """Check if idempotency should be applied to this request."""
        # Only mutating methods
        if request.method not in IDEMPOTENT_METHODS:
            return False

        # Only configured paths
        path = request.url.path
        return any(path.startswith(prefix) for prefix in self.paths)

    def _get_idempotency_key(self, request: Request) -> Optional[str]:
        """Extract and validate the idempotency key from request headers."""
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return None

        # Validate key length
        if len(key) > MAX_KEY_LENGTH:
            return None

        # Strip whitespace
        key = key.strip()
        if not key:
            return None

        return key

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request with idempotency support."""
        # Skip if this request type/path doesn't need idempotency
        if not self._should_apply(request):
            return await call_next(request)

        # Skip if no idempotency key provided
        idempotency_key = self._get_idempotency_key(request)
        if idempotency_key is None:
            return await call_next(request)

        # Skip if Redis is unavailable (graceful degradation)
        if not self.store.available:
            logger.debug(
                "Idempotency: Redis unavailable, passing through "
                "(key=%s, path=%s)",
                idempotency_key[:8],
                request.url.path,
            )
            return await call_next(request)

        # Check for cached response
        cached = await self.store.get(idempotency_key)
        if cached is not None:
            logger.info(
                "Idempotency: Returning cached response "
                "(key=%s, path=%s, status=%d)",
                idempotency_key[:8],
                request.url.path,
                cached.status_code,
            )
            response = cached.to_starlette_response()
            response.headers["X-Idempotency-Replay"] = "true"
            return response

        # Try to acquire processing lock
        lock_acquired = await self.store.acquire_lock(idempotency_key)
        if not lock_acquired:
            # Another request with the same key is currently processing.
            # Return 409 Conflict to signal the caller to retry later.
            logger.info(
                "Idempotency: Request already in progress "
                "(key=%s, path=%s)",
                idempotency_key[:8],
                request.url.path,
            )
            return JSONResponse(
                status_code=409,
                content={
                    "error": "Request with this idempotency key is already being processed",
                    "idempotency_key": idempotency_key,
                },
                headers={"Retry-After": "2"},
            )

        try:
            # Execute the actual request handler
            response = await call_next(request)

            # Read the response body so we can cache it
            body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    body += chunk.encode("utf-8")
                else:
                    body += chunk

            # Extract cacheable headers (skip hop-by-hop headers)
            cacheable_headers = {}
            for header_name, header_value in response.headers.items():
                lower = header_name.lower()
                if lower not in (
                    "transfer-encoding",
                    "connection",
                    "keep-alive",
                ):
                    cacheable_headers[header_name] = header_value

            # Cache the response
            cached_response = CachedResponse(
                status_code=response.status_code,
                headers=cacheable_headers,
                body=body,
            )
            await self.store.set(
                idempotency_key, cached_response, self.ttl_seconds
            )

            # Return a new response with the read body
            new_response = Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
            new_response.headers["X-Idempotency-Key-Accepted"] = "true"
            return new_response

        finally:
            # Always release the lock
            await self.store.release_lock(idempotency_key)
