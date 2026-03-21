"""
Scheduler rate limiting — Redis-backed with in-memory fallback.

Provides _check_rate_limit() for public booking endpoints and
_get_client_ip() for audit logging.
"""

from fastapi import HTTPException, Request
from collections import OrderedDict, deque
import asyncio
import ipaddress
import logging
import os
import time as _time

logger = logging.getLogger(__name__)


# ============================================================================
# IP HELPERS
# ============================================================================

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/internal range (RFC 1918, loopback, ULA)."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


def _parse_trusted_proxy_cidrs() -> list:
    """Parse TRUSTED_PROXY_CIDRS env var into a list of ipaddress networks.
    Defaults include RFC 1918/loopback ranges (covers Railway, Docker, local dev)
    and Cloudflare's primary IPv4 ranges."""
    default_cidrs = (
        "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,"
        "::1/128,fc00::/7,"
        # Cloudflare IPv4 ranges (subset — covers most deployments)
        "173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,"
        "141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,"
        "197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,"
        "104.24.0.0/14,172.64.0.0/13,131.0.72.0/22"
    )
    raw = os.getenv("TRUSTED_PROXY_CIDRS", default_cidrs)
    networks = []
    for cidr in raw.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning(f"Invalid CIDR in TRUSTED_PROXY_CIDRS, skipping: {cidr}")
    return networks


_TRUSTED_PROXY_CIDRS = _parse_trusted_proxy_cidrs()


def _is_trusted_proxy(ip_str: str) -> bool:
    """Check if an IP address belongs to a trusted proxy network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _TRUSTED_PROXY_CIDRS)
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from a request.

    Only trusts X-Forwarded-For when the direct connecting IP (request.client.host)
    belongs to a trusted proxy network (Railway, Cloudflare, or private/internal).
    Uses the rightmost (last) IP in X-Forwarded-For, which is the one appended by
    the closest trusted proxy and is hardest to spoof.
    Falls back to the direct connection IP if the header can't be trusted.
    """
    direct_ip = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and _is_trusted_proxy(direct_ip):
        # Request came through a trusted proxy; use the rightmost (last) IP
        # which was appended by the closest trusted reverse proxy
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        if ips:
            return ips[-1]

    return direct_ip


# ============================================================================
# RATE LIMIT CONFIGURATION
# ============================================================================

_RATE_LIMIT_WINDOW = int(os.getenv("SCHEDULER_RATE_LIMIT_WINDOW", os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
_RATE_LIMIT_MAX_PUBLIC = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX", os.getenv("RATE_LIMIT_MAX_PUBLIC", "10")))
_RATE_LIMIT_MAX_AUTHENTICATED = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX_AUTH", "60"))

# Lazy Redis connection for rate limiting
_rate_limit_redis = None
_rate_limit_redis_checked = False


def _get_rate_limit_redis():
    """Get or create Redis connection for rate limiting. Returns None if unavailable."""
    global _rate_limit_redis, _rate_limit_redis_checked

    # Check for test monkey-patches on re-export modules (tests set sar._rate_limit_redis)
    import sys as _sys
    for _mod_name in ('routes.scheduler._helpers', 'routes.scheduler_appointment_routes'):
        _mod = _sys.modules.get(_mod_name)
        if _mod is not None and '_rate_limit_redis_checked' in _mod.__dict__:
            if _mod.__dict__['_rate_limit_redis_checked']:
                return _mod.__dict__.get('_rate_limit_redis')

    if _rate_limit_redis_checked:
        return _rate_limit_redis
    _rate_limit_redis_checked = True
    try:
        import redis as redis_lib
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _rate_limit_redis = redis_lib.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2
        )
        _rate_limit_redis.ping()
        logger.info("Scheduler rate limiter connected to Redis")
    except Exception as e:
        logger.warning(f"Redis unavailable for scheduler rate limiting: {e}")
        _rate_limit_redis = None
    return _rate_limit_redis


# In-memory rate limiter fallback when Redis is unavailable
# Uses OrderedDict for LRU-style eviction to bound memory usage.
_memory_rate_limits: OrderedDict = OrderedDict()  # key -> deque of timestamps
_memory_rate_lock = asyncio.Lock()  # asyncio.Lock for async FastAPI context (threading.Lock can deadlock)
_memory_rate_check_count = 0  # Counter for periodic cleanup
_MAX_RATE_LIMIT_KEYS = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX_KEYS", "10000"))
_MEMORY_CLEANUP_INTERVAL = int(os.getenv("SCHEDULER_RATE_LIMIT_CLEANUP_INTERVAL",
                                          os.getenv("RATE_LIMIT_CLEANUP_INTERVAL", "500")))


class _RateLimitCapacityExhausted(Exception):
    """Raised when the in-memory rate limiter has no capacity for new keys."""
    pass


async def _check_memory_rate_limit(key: str, max_requests: int, window_seconds: int = _RATE_LIMIT_WINDOW) -> bool:
    """
    In-memory sliding window rate limit. Returns True if allowed, False if over limit.
    Raises _RateLimitCapacityExhausted if the in-memory store is full and the key is
    not already tracked (cannot safely admit new clients).

    Uses asyncio.Lock for safe use in async FastAPI handlers. Not multi-process safe
    (per-worker protection only).

    Uses an OrderedDict with LRU ordering: accessed keys are moved to the end.
    Periodically purges keys whose timestamp deques are empty. When the store is at
    capacity and a genuinely new key arrives, we raise instead of silently evicting
    -- evicting would destroy rate-limit state for existing clients, effectively
    bypassing protection for rotated IPs.
    """
    global _memory_rate_check_count
    now = _time.time()
    async with _memory_rate_lock:
        # Periodic cleanup first: remove keys with empty deques to free capacity
        _memory_rate_check_count += 1
        if _memory_rate_check_count >= _MEMORY_CLEANUP_INTERVAL:
            _memory_rate_check_count = 0
            empty_keys = [k for k, v in _memory_rate_limits.items() if not v]
            for k in empty_keys:
                del _memory_rate_limits[k]
            if empty_keys:
                logger.debug(f"Rate limiter cleanup: evicted {len(empty_keys)} expired keys")

        if key in _memory_rate_limits:
            timestamps = _memory_rate_limits[key]
            # Move to end (most recently accessed) for LRU ordering
            _memory_rate_limits.move_to_end(key)
        else:
            # New key -- check capacity before inserting.
            # SECURITY: Do NOT silently evict old entries to make room. Evicting
            # destroys rate-limit state for those clients, which means an attacker
            # rotating source IPs could flush legitimate tracking entries and never
            # be rate-limited. Instead, refuse new keys when at capacity.
            if len(_memory_rate_limits) >= _MAX_RATE_LIMIT_KEYS:
                raise _RateLimitCapacityExhausted(
                    f"In-memory rate limiter at capacity ({_MAX_RATE_LIMIT_KEYS} keys). "
                    "Cannot track new clients safely."
                )
            timestamps = deque()
            _memory_rate_limits[key] = timestamps

        # Evict expired timestamps from this key's deque
        while timestamps and timestamps[0] < now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return False
        timestamps.append(now)

        return True


async def _check_rate_limit(request: Request, max_requests: int = _RATE_LIMIT_MAX_PUBLIC, custom_key: str = None):
    """
    Redis-backed rate limiter keyed by client IP + path.
    Falls back to async in-memory rate limiting if Redis is unavailable.

    Args:
        request: The incoming HTTP request (used for IP and path extraction).
        max_requests: Maximum requests allowed in the rate-limit window.
        custom_key: Optional override for the rate-limit key. When provided,
                    this replaces the default ``sched_rl:{path}:{ip}`` key,
                    allowing callers to rate-limit by a different dimension
                    (e.g., per-email or per-action).

    SECURITY RATIONALE: Public booking endpoints (no auth required) are the primary
    consumers of this function. If rate limiting is completely bypassed, these
    endpoints are vulnerable to:
      - Brute-force appointment enumeration and scraping
      - Denial-of-service via booking slot exhaustion
      - Spam booking / resource exhaustion attacks
    Therefore, when Redis is unavailable, we use an in-memory fallback with bounded
    capacity. If the fallback is also exhausted (too many distinct client keys), we
    return HTTP 503 rather than silently allowing unlimited requests. Availability
    is less important than allowing unbounded abuse of public endpoints.
    """
    client_ip = _get_client_ip(request)

    key = custom_key or f"sched_rl:{request.url.path}:{client_ip}"

    r = _get_rate_limit_redis()
    if r is None:
        # Fallback: in-memory rate limiting (per-worker only -- degraded protection).
        # The effective limit is multiplied by worker count since each process has
        # its own in-memory store.
        logger.warning("Rate limiter: Redis unavailable, using per-worker memory fallback. "
                        "Effective limit is multiplied by worker count. Restore Redis ASAP.")
        try:
            if not await _check_memory_rate_limit(key, max_requests):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
                )
        except _RateLimitCapacityExhausted:
            # SECURITY: In-memory fallback is full and cannot track this new client.
            # Refusing the request (503) is safer than allowing it through unmetered.
            # This scenario indicates Redis has been down long enough for the fallback
            # to accumulate _MAX_RATE_LIMIT_KEYS distinct clients -- an operational
            # emergency that needs immediate attention.
            logger.error(
                "Rate limiter: in-memory fallback capacity exhausted "
                f"({_MAX_RATE_LIMIT_KEYS} keys). Rejecting request with 503. "
                "Restore Redis immediately to resume normal operation."
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later.",
                headers={"Retry-After": "30"}
            )
        return

    try:
        current = r.incr(key)
        if current == 1:
            r.expire(key, _RATE_LIMIT_WINDOW)
        if current > max_requests:
            ttl = r.ttl(key)
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(max(ttl, 1))}
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis command error mid-request -- fall back to in-memory
        logger.warning(f"Rate limit Redis error, using memory fallback: {e}")
        try:
            if not await _check_memory_rate_limit(key, max_requests):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
                )
        except _RateLimitCapacityExhausted:
            logger.error(
                "Rate limiter: in-memory fallback capacity exhausted "
                f"({_MAX_RATE_LIMIT_KEYS} keys). Rejecting request with 503. "
                "Restore Redis immediately to resume normal operation."
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later.",
                headers={"Retry-After": "30"}
            )
