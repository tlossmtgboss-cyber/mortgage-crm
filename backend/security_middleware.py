"""
Security middleware for the Mortgage CRM application
Protects against common web vulnerabilities and attacks
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict
import re
import logging
from typing import Dict, Tuple
import time

logger = logging.getLogger(__name__)

# ============================================================================
# RATE LIMITING MIDDLEWARE
# ============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting to prevent brute force attacks and DDoS
    Tracks requests per IP address
    """

    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        # Store: {ip: [(timestamp, path), ...]}
        self.request_history: Dict[str, list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        current_time = time.time()

        # Clean old entries for this IP
        self.request_history[client_ip] = [
            (ts, path) for ts, path in self.request_history[client_ip]
            if current_time - ts < 3600  # Keep last hour
        ]

        # Check rate limits
        recent_requests = self.request_history[client_ip]

        # Check per-minute limit
        minute_ago = current_time - 60
        requests_last_minute = sum(1 for ts, _ in recent_requests if ts > minute_ago)

        if requests_last_minute >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for IP {client_ip}: {requests_last_minute} requests/min")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": 60
                }
            )

        # Check per-hour limit
        hour_ago = current_time - 3600
        requests_last_hour = sum(1 for ts, _ in recent_requests if ts > hour_ago)

        if requests_last_hour >= self.requests_per_hour:
            logger.warning(f"Hourly rate limit exceeded for IP {client_ip}: {requests_last_hour} requests/hour")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Hourly rate limit exceeded. Please try again later.",
                    "retry_after": 3600
                }
            )

        # Add this request to history
        self.request_history[client_ip].append((current_time, str(request.url.path)))

        response = await call_next(request)
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, accounting for proxies"""
        # Check for forwarded IP (from proxies/load balancers)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses
    Protects against XSS, clickjacking, MIME sniffing, etc.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Content Security Policy - Prevents XSS attacks
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.openai.com https://api.anthropic.com https://graph.microsoft.com; "
            "frame-ancestors 'none';"
        )

        # Prevent clickjacking attacks
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
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
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
    """

    def __init__(self, app):
        super().__init__(app)
        # Track failed login attempts per IP
        self.failed_attempts: Dict[str, list] = defaultdict(list)
        self.blocked_ips: set = set()

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)

        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            logger.warning(f"Blocked request from banned IP: {client_ip}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied"}
            )

        # Check for suspicious patterns in URL
        if self._is_suspicious_request(request):
            logger.warning(f"Suspicious request from {client_ip}: {request.url.path}")
            self.blocked_ips.add(client_ip)
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
            self.blocked_ips.add(ip)


# ============================================================================
# REQUEST VALIDATION MIDDLEWARE
# ============================================================================

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate and sanitize incoming requests
    """

    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
            logger.warning(f"Request too large: {content_length} bytes from {request.client.host}")
            return JSONResponse(
                status_code=413,
                content={"detail": "Request entity too large"}
            )

        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            allowed_types = [
                "application/json",
                "application/x-www-form-urlencoded",
                "multipart/form-data"
            ]

            if not any(allowed in content_type for allowed in allowed_types):
                # Skip validation for specific endpoints that might need other types
                if not request.url.path.startswith("/api/v1/documents/upload"):
                    logger.warning(f"Invalid content type: {content_type} from {request.client.host}")

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
        client_ip = request.headers.get("X-Forwarded-For", request.client.host)

        # Log authentication attempts
        if request.url.path in ["/token", "/register", "/api/v1/users/login"]:
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
