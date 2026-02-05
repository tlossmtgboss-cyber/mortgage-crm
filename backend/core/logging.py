"""
Structured Logging Configuration

Provides structured JSON logging for production observability.
Uses structlog for consistent, searchable log output.

Features:
- JSON output in production, colored console in development
- Request ID correlation across all log entries
- User ID and tenant ID (organization_id) context
- Automatic ISO timestamp and log level
- Exception formatting with stack traces
- ASGI middleware for automatic request logging

Usage:
    from core.logging import get_logger, configure_logging

    # At application startup (call once before any logging)
    configure_logging()

    # In any module
    logger = get_logger(__name__)
    logger.info("User logged in", user_id=123, email="user@example.com")

    # With bound context
    logger = logger.bind(request_id="abc-123", tenant_id="org-456")
    logger.info("Processing request")  # Includes request_id and tenant_id

    # In FastAPI middleware or routes, set context
    from core.logging import set_request_id, set_user_id, set_tenant_id
    set_request_id("correlation-123")
    set_user_id(42)
    set_tenant_id("org-789")
"""

import logging
import os
import sys
import time
import uuid
from typing import Optional, Any, Dict
from contextvars import ContextVar
from datetime import datetime, timezone

import structlog
from structlog.types import Processor

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set request ID in context."""
    request_id_var.set(request_id)


def get_user_id() -> Optional[int]:
    """Get current user ID from context."""
    return user_id_var.get()


def set_user_id(user_id: int) -> None:
    """Set user ID in context."""
    user_id_var.set(user_id)


def get_tenant_id() -> Optional[str]:
    """Get current tenant ID from context."""
    return tenant_id_var.get()


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID in context."""
    tenant_id_var.set(tenant_id)


def add_context_vars(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Add context variables to log event.

    This processor adds request_id, user_id, and tenant_id
    from context variables to every log entry.
    """
    request_id = request_id_var.get()
    user_id = user_id_var.get()
    tenant_id = tenant_id_var.get()

    if request_id:
        event_dict["request_id"] = request_id
    if user_id:
        event_dict["user_id"] = user_id
    if tenant_id:
        event_dict["tenant_id"] = tenant_id

    return event_dict


def add_timestamp(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Add ISO timestamp to log event."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_service_info(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Add service metadata to log event."""
    event_dict["service"] = "perennia-crm"
    event_dict["environment"] = os.getenv("ENVIRONMENT", "development")
    return event_dict


def configure_logging(
    level: str = None,
    json_logs: bool = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Auto-detected if not set.
        json_logs: Use JSON output. Auto-detected based on environment if not set.

    Call this once at application startup before any logging occurs.
    """
    # Auto-detect settings from environment
    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_production = environment in ("production", "prod")

    if level is None:
        level = os.getenv("LOG_LEVEL", "WARNING" if is_production else "INFO")

    if json_logs is None:
        json_logs = is_production or os.getenv("LOG_FORMAT", "").lower() == "json"

    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Define processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_timestamp,
        add_context_vars,
        add_service_info,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        # JSON output for production
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Colored console output for development
        shared_processors.append(structlog.dev.set_exc_info)
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Configure root handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(numeric_level)

    # Suppress noisy third-party loggers
    noisy_loggers = [
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy.engine",
        "httpx",
        "httpcore",
        "apscheduler",
        "apscheduler.scheduler",
        "apscheduler.executors",
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog BoundLogger

    Usage:
        logger = get_logger(__name__)
        logger.info("Event occurred", key="value")
    """
    return structlog.get_logger(name)


# Convenience function for logging middleware
def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """
    Log an HTTP request with standard fields.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        **extra: Additional fields to include
    """
    logger = get_logger("http")

    log_data = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        **extra,
    }

    if status_code >= 500:
        logger.error("Request failed", **log_data)
    elif status_code >= 400:
        logger.warning("Request error", **log_data)
    else:
        logger.info("Request completed", **log_data)


class RequestLoggingMiddleware:
    """
    ASGI middleware for request logging.

    Logs all HTTP requests with timing, status codes, and context.
    Automatically captures request_id from headers or generates one.
    Extracts user context from authenticated requests when available.

    Usage:
        from core.logging import RequestLoggingMiddleware
        app.add_middleware(RequestLoggingMiddleware)

    Or with Starlette:
        app = Starlette(middleware=[
            Middleware(RequestLoggingMiddleware),
        ])
    """

    # Paths to skip logging (health checks, metrics)
    SKIP_PATHS = frozenset({
        "/health",
        "/health/live",
        "/health/ready",
        "/api/health",
        "/metrics",
        "/favicon.ico",
    })

    def __init__(self, app):
        self.app = app
        self._logger = None

    @property
    def logger(self):
        """Lazy-load logger to ensure structlog is configured."""
        if self._logger is None:
            self._logger = get_logger("http.access")
        return self._logger

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate request ID
        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or
            headers.get(b"x-correlation-id", b"").decode() or
            str(uuid.uuid4())[:8]
        )
        set_request_id(request_id)

        # Track response status
        status_code = 500
        start_time = time.time()
        response_headers = []

        async def send_wrapper(message):
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = message.get("headers", [])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Log the exception before re-raising
            duration_ms = (time.time() - start_time) * 1000
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")

            self.logger.exception(
                "Request failed with exception",
                method=method,
                path=path,
                status_code=500,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
                exception_type=type(exc).__name__,
            )
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")
            query_string = scope.get("query_string", b"").decode()

            # Skip logging for noisy endpoints
            if path not in self.SKIP_PATHS:
                # Extract client info
                client = scope.get("client")
                client_host = client[0] if client else None

                # Get user context if available
                user_id = get_user_id()
                tenant_id = get_tenant_id()

                log_request(
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    client_ip=client_host,
                    query_string=query_string if query_string else None,
                )


# Auto-configure on import if not already done
_configured = False


def ensure_configured() -> None:
    """Ensure logging is configured (idempotent)."""
    global _configured
    if not _configured:
        configure_logging()
        _configured = True


def clear_context() -> None:
    """
    Clear all context variables.

    Call this at the end of a request to prevent context leakage
    in case the context vars aren't properly scoped.
    """
    request_id_var.set(None)
    user_id_var.set(None)
    tenant_id_var.set(None)


class LoggingContextMiddleware:
    """
    ASGI middleware that sets logging context from request state.

    This middleware should be added AFTER authentication middleware
    so that request.state.user and request.state.tenant_context are available.

    Usage:
        from core.logging import LoggingContextMiddleware, RequestLoggingMiddleware

        # Add after auth middleware, before request logging
        app.add_middleware(RequestLoggingMiddleware)  # Logs with context
        app.add_middleware(LoggingContextMiddleware)  # Sets context from auth
        app.add_middleware(AuthMiddleware)  # Authenticates user
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            # The context will be set by auth middleware via request.state
            # We check for it after the request is processed
            await self.app(scope, receive, send)
        finally:
            # Clear context to prevent leakage between requests
            clear_context()


# Export all public symbols
__all__ = [
    # Configuration
    "configure_logging",
    "ensure_configured",
    # Logger
    "get_logger",
    # Request logging
    "log_request",
    "RequestLoggingMiddleware",
    "LoggingContextMiddleware",
    # Context management
    "request_id_var",
    "user_id_var",
    "tenant_id_var",
    "get_request_id",
    "set_request_id",
    "get_user_id",
    "set_user_id",
    "get_tenant_id",
    "set_tenant_id",
    "clear_context",
]
