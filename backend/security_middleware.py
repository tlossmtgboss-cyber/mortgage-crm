"""
Security middleware for the Mortgage CRM application
Protects against common web vulnerabilities and attacks

Environment-Based Security:
- Production: Full security with IP whitelist enforcement
- Staging: Relaxed IP restrictions for testing, but other security active
- Development: All security checks disabled for local development

Test API Key:
- Set TEST_API_KEY environment variable to enable automated testing bypass
- Include X-Test-API-Key header in requests to bypass IP restrictions
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict
import re
import logging
import os
import ipaddress
from typing import Dict, Tuple, Optional, Set, List
import time
import redis

logger = logging.getLogger(__name__)

# Environment detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
TEST_API_KEY = os.getenv("TEST_API_KEY", "")

# Admin IP whitelist enforcement toggle — set to "true" in production
# once admin IPs are configured via ADMIN_IP_1/2/3 env vars.
ADMIN_IP_WHITELIST_ENABLED = os.getenv(
    "ADMIN_IP_WHITELIST_ENABLED", "false"
).strip().lower() in ("1", "true", "yes", "on")

# CORS allowed origins for rate-limit 429 responses.
# Loaded from env var RATE_LIMIT_ALLOWED_ORIGINS (comma-separated) with
# a sensible default.  Externalising makes audit and rotation easier.
_DEFAULT_RATE_LIMIT_ORIGINS = (
    "https://perenniaai.com,"
    "https://www.perenniaai.com,"
    "https://app.perenniaai.com,"
    "https://api.perenniaai.com,"
    "capacitor://localhost,"
    "ionic://localhost"
)
_RATE_LIMIT_ALLOWED_ORIGINS: set = set(
    origin.strip()
    for origin in os.getenv(
        "RATE_LIMIT_ALLOWED_ORIGINS", _DEFAULT_RATE_LIMIT_ORIGINS
    ).split(",")
    if origin.strip()
)
if ENVIRONMENT != "production":
    _RATE_LIMIT_ALLOWED_ORIGINS.update({
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
    })

# ============================================================================
# SHARED SECURITY STATE (Module-level for dashboard access)
# ============================================================================

class SecurityStats:
    """Shared state for security metrics accessible by dashboard endpoint"""
    BLOCK_DURATION = 900  # 15 minutes — matches failed-attempt window

    def __init__(self):
        self.blocked_ips: Dict[str, float] = {}  # ip -> blocked_at timestamp
        self.failed_attempts: Dict[str, list] = defaultdict(list)
        self.request_history: Dict[str, list] = defaultdict(list)
        self.suspicious_requests: list = []
        self.middleware_status: Dict[str, bool] = {
            "ip_access_control": True,
            "rate_limiting": True,
            "ip_blocking": True,
            "request_validation": True,
            "security_headers": True,
            "security_logging": True,
        }

    def get_dashboard_data(self) -> dict:
        """Get security dashboard data"""
        current_time = time.time()

        # Clean old failed attempts (older than 15 minutes)
        recent_failed = {}
        for ip, attempts in self.failed_attempts.items():
            recent = [ts for ts in attempts if current_time - ts < 900]
            if recent:
                recent_failed[ip] = len(recent)

        # Get rate limit stats
        active_rate_limits = 0
        total_requests = 0
        top_requesters = []
        for key, history in self.request_history.items():
            recent = [(ts, p) for ts, p in history if current_time - ts < 60]
            if recent:
                active_rate_limits += 1
                total_requests += len(recent)
                top_requesters.append({
                    "key": key,
                    "requests": len(recent),
                    "last_request": max(ts for ts, _ in recent) if recent else 0
                })

        # Sort top requesters
        top_requesters.sort(key=lambda x: x["requests"], reverse=True)

        return {
            "status": "active",
            "environment": ENVIRONMENT,
            "middleware_status": self.middleware_status,
            "ip_blocking": {
                "blocked_count": len(self.blocked_ips),
                "blocked_ips": list(self.blocked_ips.keys())[:50],
            },
            "rate_limiting": {
                "active_keys": active_rate_limits,
                "total_requests_tracked": total_requests,
                "top_requesters": top_requesters[:10],
            },
            "failed_logins": {
                "recent_failed_attempts": sum(recent_failed.values()),
                "unique_ips": len(recent_failed),
                "top_offenders": [
                    {"ip": ip, "attempts": count}
                    for ip, count in sorted(recent_failed.items(), key=lambda x: x[1], reverse=True)[:10]
                ],
            },
            "configuration": {
                "environment": ENVIRONMENT,
                "admin_ip_whitelist_enabled": ADMIN_IP_WHITELIST_ENABLED,
                "whitelisted_ips_configured": bool(WHITELISTED_IPS - {"127.0.0.1", "localhost"}),
                "test_api_key_configured": bool(TEST_API_KEY),
                "max_request_size_mb": 10,
                "failed_login_threshold": 5,
                "failed_login_window_minutes": 15,
            },
            "rate_limit_tiers": {
                "admin": {"requests_per_minute": 200, "requests_per_hour": 5000},
                "power_user": {"requests_per_minute": 100, "requests_per_hour": 2000},
                "standard": {"requests_per_minute": 60, "requests_per_hour": 1000},
                "anonymous": {"requests_per_minute": 30, "requests_per_hour": 300},
            },
        }

    def is_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked (respects expiry)"""
        if ip not in self.blocked_ips:
            return False
        if time.time() - self.blocked_ips[ip] >= self.BLOCK_DURATION:
            # Block expired — auto-clear
            del self.blocked_ips[ip]
            self.failed_attempts.pop(ip, None)
            return False
        return True

    def block_ip(self, ip: str):
        """Block an IP with timestamp"""
        self.blocked_ips[ip] = time.time()

    def unblock_ip(self, ip: str) -> bool:
        """Unblock an IP address"""
        if ip in self.blocked_ips:
            del self.blocked_ips[ip]
            self.failed_attempts.pop(ip, None)
            return True
        return False

# Global instance for shared state
security_stats = SecurityStats()

# IP Whitelist Configuration
WHITELISTED_IPS: Set[str] = set(filter(None, [
    os.getenv("ADMIN_IP_1", ""),
    os.getenv("ADMIN_IP_2", ""),
    os.getenv("ADMIN_IP_3", ""),
    "127.0.0.1",
    "localhost",
]))

# CIDR ranges for private networks (allowed in staging/dev)
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

# Paths that bypass IP restrictions (always accessible)
PUBLIC_PATHS = [
    "/health",
    "/health/ready",
    "/health/live",
    "/health/detailed",
    "/api/v1/health",  # API health check endpoint
    "/docs",
    "/redoc",
    "/openapi.json",
    "/token",  # Login endpoint - must be accessible for authentication
    "/api/v1/auth/",  # Auth endpoints
    "/api/v1/migrations/convert-lead-stage-to-enum-names",  # Key-protected migration
    "/api/v1/migrations/fix-lead-stage-values",  # Key-protected migration
    "/api/v1/webhook/",  # Webhooks must be accessible from external services (SendGrid, Telnyx, etc.)
    "/api/vapi/",  # Vapi AI receptionist webhooks — verified by require_vapi_webhook
    "/api/v1/telephony/",  # Telephony webhooks (Vapi inbound, call routing) — verified by require_vapi_webhook
    "/api/v1/referral-partners",  # May need public access for integrations
    "/api/v1/admin/account-management/cleanup/",  # Admin-key protected cleanup endpoints
    "/api/v1/admin/account-management/run-migration",  # Admin-key protected migration
    "/api/v1/admin/account-management/run-invitations-migration",  # Admin-key protected migration
    "/api/v1/admin/account-management/run-cleanup-migration",  # Admin-key protected cleanup migration
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_public_path(path: str) -> bool:
    """Check if path should be publicly accessible without IP restrictions"""
    return any(path.startswith(p) for p in PUBLIC_PATHS)


def is_ip_in_private_network(ip: str) -> bool:
    """Check if IP is in a private network range"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return any(ip_obj in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return False


def is_ip_whitelisted(ip: str) -> bool:
    """Check if IP is explicitly whitelisted"""
    return ip in WHITELISTED_IPS


def has_valid_test_api_key(request: Request) -> bool:
    """Check if request has valid test API key header"""
    if not TEST_API_KEY:
        return False
    import hmac
    api_key = request.headers.get("X-Test-API-Key", "")
    if not api_key:
        return False
    return hmac.compare_digest(api_key, TEST_API_KEY)


def is_websocket_request(request: Request) -> bool:
    """
    Check if the request is a WebSocket upgrade request
    WebSocket connections should bypass HTTP-only middleware
    """
    # Check for WebSocket upgrade header
    connection = request.headers.get("connection", "").lower()
    upgrade = request.headers.get("upgrade", "").lower()

    # Check if it's a WebSocket path
    websocket_paths = [
        "/api/v1/voice/ws/voice-stream",
        "/api/v1/meetings/ws/",  # Video meeting signaling
        "/ws/",
        "/websocket/"
    ]

    is_ws_path = any(path in str(request.url.path) for path in websocket_paths)
    is_ws_upgrade = "upgrade" in connection and upgrade == "websocket"

    return is_ws_path or is_ws_upgrade


def is_mobile_app_request(request: Request) -> bool:
    """
    Check if the request claims to be from a mobile app (Capacitor iOS/Android).
    Mobile apps send the X-Mobile-App header to identify themselves.

    WARNING: This header is trivially spoofable. It MUST NOT be used to bypass
    security controls (IP access control, IP blocking, etc.). It may be used for
    non-security purposes such as adjusting rate limits or response formatting.

    For security-sensitive decisions about mobile identity, verify via JWT claims
    (e.g., a 'platform' claim set during authentication).
    """
    mobile_app_header = request.headers.get("X-Mobile-App", "")
    valid_mobile_apps = ["capacitor-ios", "capacitor-android", "react-native"]
    return mobile_app_header in valid_mobile_apps


# ============================================================================
# IP ACCESS CONTROL MIDDLEWARE (Environment-Aware)
# ============================================================================

class IPAccessControlMiddleware(BaseHTTPMiddleware):
    """
    Environment-aware IP access control.

    Production: Strict IP whitelist enforcement
    Staging: Relaxed - allows test API key bypass and private networks
    Development: No IP restrictions

    Always allows:
    - Public paths (health checks, docs)
    - WebSocket connections
    - Requests with valid test API key (if configured)
    """

    async def dispatch(self, request: Request, call_next):
        path = str(request.url.path)

        # Always allow WebSocket connections
        if is_websocket_request(request):
            return await call_next(request)

        # NOTE: Mobile app requests are NOT exempt from IP access controls.
        # The X-Mobile-App header is trivially spoofable and must not bypass
        # security checks. Mobile apps authenticate via JWT like any other client.

        # Always allow public paths
        if is_public_path(path):
            return await call_next(request)

        # Development mode: no IP restrictions
        if ENVIRONMENT == "development":
            return await call_next(request)

        # Check for valid test API key (allows automated testing)
        if has_valid_test_api_key(request):
            logger.info(f"Access granted via test API key: {path}")
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Staging mode: allow whitelisted IPs and private networks
        if ENVIRONMENT == "staging":
            if is_ip_whitelisted(client_ip) or is_ip_in_private_network(client_ip):
                return await call_next(request)
            # In staging, log but allow (for easier testing)
            logger.info(f"Staging access from non-whitelisted IP: {client_ip}")
            return await call_next(request)

        # Production mode: IP whitelist enforcement for admin paths.
        # Controlled by ADMIN_IP_WHITELIST_ENABLED env var (default: false).
        # Set to "true" once ADMIN_IP_1/2/3 are configured in Railway.
        if ENVIRONMENT == "production":
            # Public paths that should NOT require admin auth (even under /admin/)
            public_paths = [
                "/api/v1/admin/users/activate/",  # Account activation (user not logged in yet)
                "/api/v1/invitations/accept/",    # Accept invitation (user not logged in yet)
            ]

            # Skip whitelist check for public activation/invitation paths
            if any(path.startswith(p) for p in public_paths):
                return await call_next(request)

            # Only enforce whitelist for admin-level endpoints
            admin_paths = ["/api/v1/admin/", "/api/v1/migrations/"]
            is_admin_path = any(path.startswith(p) for p in admin_paths)

            if is_admin_path and ADMIN_IP_WHITELIST_ENABLED:
                if is_ip_whitelisted(client_ip):
                    return await call_next(request)
                # Also allow Railway internal IPs (100.64.x.x range)
                if client_ip.startswith("100.64."):
                    return await call_next(request)

                # Allow authenticated requests from our frontend
                origin = request.headers.get("origin", "")
                referer = request.headers.get("referer", "")
                auth_header = request.headers.get("authorization", "")

                allowed_origins = [
                    "https://www.perenniaai.com",
                    "https://perenniaai.com",
                    "https://app.perenniaai.com",
                    "http://localhost:3000",
                ]

                is_allowed_origin = any(
                    origin.startswith(ao) or referer.startswith(ao)
                    for ao in allowed_origins
                )

                # If request is from our frontend with auth, allow it
                if is_allowed_origin and auth_header.startswith("Bearer "):
                    logger.info(f"Admin access granted via frontend origin: {origin or referer}")
                    return await call_next(request)

                logger.warning(f"Admin access denied for IP {client_ip}: {request.method} {path}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied - admin access requires whitelisted IP"}
                )
            elif is_admin_path and not ADMIN_IP_WHITELIST_ENABLED:
                logger.debug(
                    "Admin IP whitelist not enforced (ADMIN_IP_WHITELIST_ENABLED=false): "
                    f"{client_ip} -> {request.method} {path}"
                )

            # Allow all other paths in production (normal API traffic)
            return await call_next(request)

        # Default: allow (unknown environment)
        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, accounting for proxies"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"


# ============================================================================
# RATE LIMITING MIDDLEWARE - Per-User and Per-IP Rate Limiting
# ============================================================================

# Rate limit tiers based on user roles
RATE_LIMIT_TIERS = {
    # Admin users get highest limits
    "admin": {"requests_per_minute": 1000, "requests_per_hour": 50000},
    # Power users (managers, senior LOs) get elevated limits
    "power_user": {"requests_per_minute": 600, "requests_per_hour": 30000},
    # Standard authenticated users
    "standard": {"requests_per_minute": 300, "requests_per_hour": 15000},
    # Unauthenticated/IP-based (most restrictive)
    "anonymous": {"requests_per_minute": 100, "requests_per_hour": 2000},
}

# Endpoint categories with specific rate limits (multipliers applied to base limits)
ENDPOINT_RATE_LIMITS = {
    # Auth endpoints - strict limits to prevent brute force (anonymous: 100/min base)
    "/token": {"multiplier": 0.3, "burst_allowed": 10},              # 30/min, 10 per 10s (accounts for CORS preflight + retries)
    "/api/v1/auth/login": {"multiplier": 0.3, "burst_allowed": 10},  # Same limits as /token
    "/api/v1/auth/forgot-password": {"multiplier": 0.03, "burst_allowed": 2},  # 3/min
    "/api/v1/auth/reset-password": {"multiplier": 0.05, "burst_allowed": 3},
    "/api/v1/auth/register": {"multiplier": 0.05, "burst_allowed": 2},
    "/api/v1/auth/validate-promo": {"multiplier": 0.1, "burst_allowed": 5},
    "/api/v1/setup-admin": {"multiplier": 0.02, "burst_allowed": 1},  # 2/min, 1 per 10s
    "/api/v1/borrower-auth/email/request": {"multiplier": 0.03, "burst_allowed": 2},
    "/api/v1/auth/portal/send-link": {"multiplier": 0.03, "burst_allowed": 2},
    "/api/v1/auth/portal/verify": {"multiplier": 0.05, "burst_allowed": 3},
    "/api/v1/admin/force-password-reset": {"multiplier": 0.02, "burst_allowed": 1},
    # AI endpoints are expensive - lower limits
    "/api/v1/ai/": {"multiplier": 0.2, "burst_allowed": 5},
    "/api/v1/chat/": {"multiplier": 0.3, "burst_allowed": 10},
    "/api/v1/blog/generate": {"multiplier": 0.1, "burst_allowed": 2},
    # File uploads - moderate limits
    "/api/v1/documents/upload": {"multiplier": 0.5, "burst_allowed": 20},
    "/api/v1/smart-docs/upload": {"multiplier": 0.5, "burst_allowed": 20},
    # SMS/email sending - strict limits to prevent financial abuse
    "/api/v1/sms-intelligence/send/bulk": {"multiplier": 0.02, "burst_allowed": 1},
    "/api/v1/sms-intelligence/send": {"multiplier": 0.05, "burst_allowed": 3},
    "/api/v1/conversation-intelligence/send-sms": {"multiplier": 0.05, "burst_allowed": 3},
    "/api/v1/email-drafts/send": {"multiplier": 0.1, "burst_allowed": 5},
    "/api/v1/voicemail-drop/campaigns": {"multiplier": 0.05, "burst_allowed": 2},
    # Standard API calls - normal limits (must be LAST - catch-all prefix)
    "/api/v1/": {"multiplier": 1.0, "burst_allowed": 100},
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Enhanced rate limiting with per-user and per-IP tracking.

    Features:
    - Per-user rate limiting for authenticated requests (via JWT)
    - Per-IP rate limiting for unauthenticated requests
    - Role-based rate limit tiers (admin, power_user, standard, anonymous)
    - Endpoint-specific rate limits (AI endpoints get lower limits)
    - Mobile app detection with adjusted limits
    - Burst protection for expensive endpoints
    - Redis-backed counters for cross-worker consistency (falls back to
      in-memory if Redis is unavailable)
    """

    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.base_requests_per_minute = requests_per_minute
        self.base_requests_per_hour = requests_per_hour
        # Use shared state for dashboard access (used by in-memory fallback path)
        self.request_history = security_stats.request_history
        # Cache user roles to avoid repeated JWT decoding: {user_id: (role, expiry_time)}
        self.user_role_cache: Dict[int, Tuple[str, float]] = {}
        self.role_cache_ttl = 300  # Cache roles for 5 minutes
        # Track burst windows for expensive endpoints: {key: [(timestamp, endpoint_category), ...]}
        self.burst_history: Dict[str, list] = defaultdict(list)
        # Redis client — None means fall back to in-memory counters
        self._redis: Optional[redis.Redis] = None
        self._redis_available: bool = False
        self._connect_redis()

    def _connect_redis(self) -> None:
        """Attempt to connect to Redis; log a warning and fall back to in-memory on failure."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            self._redis = client
            self._redis_available = True
            logger.info("RateLimitMiddleware: Redis connected — using Redis-backed counters")
        except Exception as e:
            self._redis = None
            self._redis_available = False
            logger.warning(
                f"RateLimitMiddleware: Redis unavailable ({e}); "
                "falling back to in-memory rate limit counters (not shared across workers)"
            )

    def _redis_check_and_increment(
        self,
        rate_limit_key: str,
        per_minute_limit: int,
        per_hour_limit: int,
        current_time: float,
    ) -> Tuple[int, int, bool, bool]:
        """
        Use Redis INCR+EXPIRE to atomically count requests within each window.

        Returns (requests_last_minute, requests_last_hour, minute_exceeded, hour_exceeded).
        Raises redis.RedisError on failure so the caller can fall back to in-memory.
        """
        minute_window = int(current_time // 60)
        hour_window = int(current_time // 3600)

        minute_redis_key = f"ratelimit:{rate_limit_key}:{minute_window}"
        hour_redis_key = f"ratelimit:{rate_limit_key}:{hour_window}"

        pipe = self._redis.pipeline()
        pipe.incr(minute_redis_key)
        pipe.expire(minute_redis_key, 120)   # 2-minute TTL — keeps one extra window for safety
        pipe.incr(hour_redis_key)
        pipe.expire(hour_redis_key, 7200)    # 2-hour TTL
        results = pipe.execute()

        requests_last_minute = int(results[0])
        requests_last_hour = int(results[2])

        minute_exceeded = requests_last_minute > per_minute_limit
        hour_exceeded = requests_last_hour > per_hour_limit

        return requests_last_minute, requests_last_hour, minute_exceeded, hour_exceeded

    async def dispatch(self, request: Request, call_next):
        path = str(request.url.path)

        # Skip rate limiting in development mode
        if ENVIRONMENT == "development":
            return await call_next(request)

        # Skip rate limiting for WebSocket connections
        if is_websocket_request(request):
            logger.debug(f"Bypassing rate limit for WebSocket: {path}")
            return await call_next(request)

        # Skip rate limiting for exempt paths
        rate_limit_exempt_paths = [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/public/",
            "/api/v1/webhook/",
            "/api/vapi/",
            "/api/v1/telephony/",
            "/api/v1/borrower/",
            "/api/v1/pos/",
            "/lo/",
            "/portal/",
            "/api/portal/",
        ]
        if any(path.startswith(p) for p in rate_limit_exempt_paths):
            return await call_next(request)

        # Extract user info from JWT if present
        user_id, user_role = self._extract_user_from_token(request)

        # Determine rate limit key (user-based or IP-based)
        if user_id:
            rate_limit_key = f"user:{user_id}"
            tier = self._get_user_tier(user_id, user_role)
        else:
            client_ip = self._get_client_ip(request)
            rate_limit_key = f"ip:{client_ip}"
            tier = "anonymous"

        # Get tier limits
        tier_config = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["anonymous"])
        per_minute_limit = tier_config["requests_per_minute"]
        per_hour_limit = tier_config["requests_per_hour"]

        # Apply endpoint-specific multipliers
        endpoint_config = self._get_endpoint_config(path)
        if endpoint_config:
            per_minute_limit = int(per_minute_limit * endpoint_config["multiplier"])
            per_hour_limit = int(per_hour_limit * endpoint_config["multiplier"])

        # Mobile apps get higher limits (carrier NAT shares IPs).
        # NOTE: This uses the spoofable X-Mobile-App header, which is acceptable
        # here because adjusting rate limits upward is NOT a security bypass --
        # the worst case is an attacker gets 2x rate limits, which is still
        # well within acceptable bounds. Security controls (IP blocking, access
        # control) are enforced regardless.
        is_mobile = is_mobile_app_request(request)
        if is_mobile:
            per_minute_limit = int(per_minute_limit * 2)
            per_hour_limit = int(per_hour_limit * 2)

        current_time = time.time()

        # CORS headers for 429 responses — validated against the module-level
        # _RATE_LIMIT_ALLOWED_ORIGINS set (loaded from RATE_LIMIT_ALLOWED_ORIGINS
        # env var at startup).  DynamicCORSMiddleware wraps us and will add its
        # own CORS headers, but 429 responses short-circuit before reaching it,
        # so we must set headers here for the browser to read the error body.
        # Allowed origins loaded from RATE_LIMIT_ALLOWED_ORIGINS env var at module level.
        origin = request.headers.get("origin", "")
        cors_origin = origin if origin in _RATE_LIMIT_ALLOWED_ORIGINS else ""
        cors_headers = {}
        if cors_origin:
            cors_headers = {
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
                "Access-Control-Allow-Headers": "Accept, Authorization, Content-Type, X-Requested-With, X-CSRF-Token, X-Request-ID, X-API-Key",
            }

        # Check burst limit for expensive endpoints (always in-memory — 10-second window)
        if endpoint_config and endpoint_config.get("burst_allowed"):
            burst_key = f"{rate_limit_key}:{path.split('/')[3] if len(path.split('/')) > 3 else 'api'}"
            self.burst_history[burst_key] = [
                ts for ts in self.burst_history[burst_key]
                if current_time - ts < 10  # 10-second burst window
            ]
            if len(self.burst_history[burst_key]) >= endpoint_config["burst_allowed"]:
                logger.warning(f"Burst limit exceeded for {rate_limit_key} on {path}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests to this endpoint. Please slow down.",
                        "retry_after": 10,
                        "limit_type": "burst"
                    },
                    headers=cors_headers
                )
            self.burst_history[burst_key].append(current_time)

        # ------------------------------------------------------------------ #
        # Per-minute / per-hour counters — Redis-backed with in-memory fallback
        # ------------------------------------------------------------------ #
        use_redis = self._redis_available and self._redis is not None

        if use_redis:
            try:
                requests_last_minute, requests_last_hour, minute_exceeded, hour_exceeded = (
                    self._redis_check_and_increment(
                        rate_limit_key, per_minute_limit, per_hour_limit, current_time
                    )
                )
            except redis.RedisError as exc:
                logger.warning(
                    f"RateLimitMiddleware: Redis error during rate check ({exc}); "
                    "falling back to in-memory for this request"
                )
                use_redis = False

        if not use_redis:
            # In-memory fallback: clean old entries, then count
            self.request_history[rate_limit_key] = [
                (ts, p) for ts, p in self.request_history[rate_limit_key]
                if current_time - ts < 3600
            ]
            recent_requests = self.request_history[rate_limit_key]
            minute_ago = current_time - 60

            requests_last_minute = sum(1 for ts, _ in recent_requests if ts > minute_ago)
            requests_last_hour = len(recent_requests)

            minute_exceeded = requests_last_minute >= per_minute_limit
            hour_exceeded = requests_last_hour >= per_hour_limit

        # Check per-minute limit
        if minute_exceeded:
            log_identifier = f"user {user_id}" if user_id else f"IP {self._get_client_ip(request)}"
            logger.warning(
                f"Rate limit exceeded for {log_identifier}: "
                f"{requests_last_minute}/{per_minute_limit} requests/min"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": 60,
                    "limit_type": "per_minute",
                    "current": requests_last_minute,
                    "limit": per_minute_limit
                },
                headers=cors_headers
            )

        # Check per-hour limit
        if hour_exceeded:
            log_identifier = f"user {user_id}" if user_id else f"IP {self._get_client_ip(request)}"
            logger.warning(
                f"Hourly rate limit exceeded for {log_identifier}: "
                f"{requests_last_hour}/{per_hour_limit} requests/hour"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Hourly rate limit exceeded. Please try again later.",
                    "retry_after": 3600,
                    "limit_type": "per_hour",
                    "current": requests_last_hour,
                    "limit": per_hour_limit
                },
                headers=cors_headers
            )

        # Record this request in the in-memory history (only for the fallback path;
        # the Redis path uses atomic INCR so no separate write is needed)
        if not use_redis:
            self.request_history[rate_limit_key].append((current_time, path))

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(per_minute_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, per_minute_limit - requests_last_minute - 1))
        response.headers["X-RateLimit-Reset"] = str(int(current_time + 60))
        if user_id:
            response.headers["X-RateLimit-Tier"] = tier

        return response

    def _extract_user_from_token(self, request: Request) -> Tuple[Optional[int], Optional[str]]:
        """Extract user ID and role from JWT token if present.

        Uses the centralized auth.tokens.verify_access_token() which handles
        RS256/HS256 algorithm selection and token blacklist checks.
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None, None

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            from auth.tokens import verify_access_token
            payload = verify_access_token(token)
            if not payload:
                return None, None

            # Extract user info from token
            user_id = payload.get("user_id") or payload.get("sub")
            if isinstance(user_id, str) and "@" in user_id:
                # Email in sub, need to look up user_id from claims or return None
                user_id = payload.get("user_id")

            user_role = payload.get("role", "Loan Officer")

            if user_id:
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    return None, None

            return user_id, user_role

        except Exception as e:
            # Invalid token - treat as anonymous
            logger.debug(f"Failed to decode JWT for rate limiting: {e}")
            return None, None

    def _get_user_tier(self, user_id: int, role: Optional[str]) -> str:
        """Determine rate limit tier based on user role."""
        current_time = time.time()

        # Check cache first
        if user_id in self.user_role_cache:
            cached_tier, expiry = self.user_role_cache[user_id]
            if current_time < expiry:
                return cached_tier

        # Determine tier based on role
        if role:
            role_lower = role.lower()
            if role_lower in ("admin", "superadmin", "super_admin", "system_admin"):
                tier = "admin"
            elif role_lower in ("manager", "branch_manager", "regional_manager", "senior_loan_officer"):
                tier = "power_user"
            else:
                tier = "standard"
        else:
            tier = "standard"

        # Cache the result
        self.user_role_cache[user_id] = (tier, current_time + self.role_cache_ttl)

        return tier

    def _get_endpoint_config(self, path: str) -> Optional[Dict]:
        """Get rate limit config for specific endpoint."""
        for endpoint_prefix, config in ENDPOINT_RATE_LIMITS.items():
            if path.startswith(endpoint_prefix):
                return config
        return None

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, accounting for proxies."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    def get_rate_limit_stats(self, rate_limit_key: str) -> Dict:
        """Get current rate limit stats for a key (for debugging/monitoring)."""
        current_time = time.time()

        if self._redis_available and self._redis is not None:
            try:
                minute_window = int(current_time // 60)
                hour_window = int(current_time // 3600)
                minute_redis_key = f"ratelimit:{rate_limit_key}:{minute_window}"
                hour_redis_key = f"ratelimit:{rate_limit_key}:{hour_window}"
                pipe = self._redis.pipeline()
                pipe.get(minute_redis_key)
                pipe.get(hour_redis_key)
                results = pipe.execute()
                return {
                    "key": rate_limit_key,
                    "requests_last_minute": int(results[0] or 0),
                    "requests_last_hour": int(results[1] or 0),
                    "backend": "redis",
                }
            except redis.RedisError as exc:
                logger.warning(f"RateLimitMiddleware: Redis error in get_rate_limit_stats ({exc})")

        # Fallback to in-memory history
        history = self.request_history.get(rate_limit_key, [])
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        return {
            "key": rate_limit_key,
            "requests_last_minute": sum(1 for ts, _ in history if ts > minute_ago),
            "requests_last_hour": sum(1 for ts, _ in history if ts > hour_ago),
            "total_tracked": len(history),
            "backend": "memory",
        }

    def clear_rate_limit(self, rate_limit_key: str) -> bool:
        """Clear rate limit for a specific key (admin function)."""
        cleared = False

        if self._redis_available and self._redis is not None:
            try:
                current_time = time.time()
                minute_window = int(current_time // 60)
                hour_window = int(current_time // 3600)
                deleted = self._redis.delete(
                    f"ratelimit:{rate_limit_key}:{minute_window}",
                    f"ratelimit:{rate_limit_key}:{hour_window}",
                )
                cleared = deleted > 0
            except redis.RedisError as exc:
                logger.warning(f"RateLimitMiddleware: Redis error in clear_rate_limit ({exc})")

        if rate_limit_key in self.request_history:
            del self.request_history[rate_limit_key]
            cleared = True

        return cleared


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses
    Protects against XSS, clickjacking, MIME sniffing, etc.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip security headers for WebSocket connections
        if is_websocket_request(request):
            logger.info(f"Bypassing security headers for WebSocket: {request.url.path}")
            return await call_next(request)

        response = await call_next(request)

        # Content Security Policy - Prevents XSS attacks
        # Allow embedding from www.perenniaai.com for /embed/ routes (booking widget)
        is_embed_route = request.url.path.startswith("/embed/")
        if is_embed_route:
            frame_policy = "frame-ancestors https://www.perenniaai.com https://perenniaai.com;"
        else:
            frame_policy = "frame-ancestors 'none';"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.perenniaai.com https://api.openai.com https://api.anthropic.com https://graph.microsoft.com; "
            f"{frame_policy}"
        )

        # Prevent clickjacking attacks (allow embedding for /embed/ routes)
        if is_embed_route:
            response.headers["X-Frame-Options"] = "ALLOW-FROM https://www.perenniaai.com"
        else:
            response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (formerly Feature-Policy)
        # microphone=(self) allows voice AI (Aria) within our own origin
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(self), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=()"
        )

        return response


# ============================================================================
# IP BLOCKING MIDDLEWARE
# ============================================================================

class IPBlockingMiddleware(BaseHTTPMiddleware):
    """
    Block known malicious IPs and suspicious patterns
    Uses shared security_stats for dashboard visibility
    """

    def __init__(self, app):
        super().__init__(app)
        # Use shared state for dashboard access
        self.failed_attempts = security_stats.failed_attempts

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip IP blocking for public paths (webhooks, health checks, etc.)
        if is_public_path(path):
            return await call_next(request)

        # Skip IP blocking for WebSocket connections
        if is_websocket_request(request):
            logger.info(f"Bypassing IP blocking checks for WebSocket: {path}")
            return await call_next(request)

        # NOTE: Mobile app requests are NOT exempt from IP blocking.
        # The X-Mobile-App header is trivially spoofable and must not bypass
        # security checks. If a mobile IP gets blocked due to suspicious
        # activity, that block is legitimate and should be enforced.

        client_ip = self._get_client_ip(request)
        logger.info(f"IPBlockingMiddleware: client_ip={client_ip}, path={path}")

        # Skip IP blocking for localhost in development mode
        environment = os.getenv("ENVIRONMENT", "development")
        logger.info(f"IPBlockingMiddleware: environment={environment}")
        # Always allow localhost in development (clear any stale blocks)
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            logger.info(f"IPBlockingMiddleware: localhost detected, clearing blocks")
            security_stats.unblock_ip(client_ip)
            if environment == "development":
                logger.info(f"IPBlockingMiddleware: allowing localhost in development")
                return await call_next(request)

        # Check if IP is blocked (auto-expires after 15 minutes)
        if security_stats.is_blocked(client_ip):
            logger.warning(f"Blocked request from banned IP: {client_ip}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )

        # Check for suspicious patterns in URL
        if self._is_suspicious_request(request):
            logger.warning(f"Suspicious request from {client_ip}: {request.url.path}")
            security_stats.block_ip(client_ip)
            return JSONResponse(
                status_code=403,
                content={"detail": "Suspicious activity detected"}
            )

        response = await call_next(request)

        # Track failed login attempts
        if request.url.path == "/token" and response.status_code == 401:
            self._record_failed_login(client_ip)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, accounting for proxies"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    def _is_suspicious_request(self, request: Request) -> bool:
        """Detect common attack patterns"""
        path = str(request.url.path).lower()

        # SQL injection patterns
        sql_patterns = [
            r"union.*select", r"or\s+1\s*=\s*1", r"drop\s+table",
            r"insert\s+into", r"delete\s+from", r"<script", r"javascript:",
            r"\.\.\/", r"etc/passwd", r"wp-admin", r"phpmyadmin"
        ]

        for pattern in sql_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return True

        # Check query parameters
        query_string = str(request.url.query).lower()
        for pattern in sql_patterns:
            if re.search(pattern, query_string, re.IGNORECASE):
                return True

        return False

    def _record_failed_login(self, ip: str):
        """Track failed login attempts and block after threshold"""
        current_time = time.time()

        # Clean old attempts (older than 15 minutes)
        self.failed_attempts[ip] = [
            ts for ts in self.failed_attempts[ip]
            if current_time - ts < 900
        ]

        # Add new attempt
        self.failed_attempts[ip].append(current_time)

        # Block after 5 failed attempts in 15 minutes
        if len(self.failed_attempts[ip]) >= 5:
            logger.warning(f"Blocking IP {ip} due to multiple failed login attempts")
            security_stats.block_ip(ip)


# ============================================================================
# REQUEST VALIDATION MIDDLEWARE
# ============================================================================

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate and sanitize incoming requests
    """

    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        # Skip request validation for WebSocket connections
        if is_websocket_request(request):
            logger.info(f"Bypassing request validation for WebSocket: {request.url.path}")
            return await call_next(request)

        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
            logger.warning(f"Request too large: {content_length} bytes from {request.client.host}")
            return JSONResponse(
                status_code=413,
                content={"detail": "Request entity too large"}
            )

        # Validate content type for POST/PUT requests with body
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            content_length = request.headers.get("content-length", "0")

            allowed_types = [
                "application/json",
                "application/x-www-form-urlencoded",
                "multipart/form-data",
                "text/plain",
                "text/html",
                "application/octet-stream",
            ]

            # Paths that don't require content type validation
            skip_validation_paths = [
                "/api/v1/documents/upload",
                "/api/v1/webhook/",
                "/api/vapi/",
                "/api/v1/telephony/",
                "/api/v1/voice/",
                "/api/v1/smart-docs/",
                "/api/portal/",
            ]

            # Only validate if:
            # 1. There's actually content being sent (content-length > 0)
            # 2. Content-type is specified but not in allowed list
            # 3. Path is not in skip list
            has_body = content_length != "0" and content_length != ""
            path_skip = any(request.url.path.startswith(p) for p in skip_validation_paths)

            if has_body and content_type and not path_skip:
                if not any(allowed in content_type.lower() for allowed in allowed_types):
                    # Log at debug level instead of warning to reduce noise
                    logger.debug(f"Uncommon content type: {content_type} from {request.client.host} for {request.url.path}")

        response = await call_next(request)
        return response


# ============================================================================
# LOGGING MIDDLEWARE FOR SECURITY EVENTS
# ============================================================================

class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all security-relevant events
    """

    async def dispatch(self, request: Request, call_next):
        # Log WebSocket connections but don't apply HTTP-specific logging
        if is_websocket_request(request):
            logger.info(f"WebSocket connection: {request.url.path}")
            return await call_next(request)

        client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")

        # Log authentication attempts
        if request.url.path in ["/token", "/api/v1/auth/login", "/register", "/api/v1/users/login"]:
            logger.info(f"Auth attempt from {client_ip}: {request.method} {request.url.path}")

        # Log sensitive operations
        sensitive_paths = [
            "/api/v1/users", "/api/v1/branches", "/api/v1/settings",
            "/api/v1/integrations", "/admin"
        ]

        if any(path in str(request.url.path) for path in sensitive_paths):
            logger.info(f"Sensitive operation from {client_ip}: {request.method} {request.url.path}")

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        # Log slow requests (potential attacks)
        if process_time > 5:
            logger.warning(f"Slow request ({process_time:.2f}s) from {client_ip}: {request.url.path}")

        # Log failed requests
        if response.status_code >= 400:
            logger.warning(
                f"Failed request from {client_ip}: "
                f"{request.method} {request.url.path} -> {response.status_code}"
            )

        return response
