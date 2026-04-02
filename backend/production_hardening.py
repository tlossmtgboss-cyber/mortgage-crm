"""
Production Hardening Utilities
==============================
Centralized module for production-ready features:
- Sentry error tracking
- Structured JSON logging
- Request ID tracing
- Enhanced rate limiting
- Health checks with dependency status
"""

import os
import sys
import uuid
import time
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# ============================================================================
# CONFIGURATION
# ============================================================================

# Sentry DSN - must be set in production
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
RELEASE_VERSION = os.getenv("RELEASE_VERSION", "unknown")

# Validate SECRET_KEY in production
SECRET_KEY = os.getenv("SECRET_KEY")
if ENVIRONMENT == "production" and not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is required in production. "
        "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# Require SECRET_KEY in all non-development environments
if not SECRET_KEY:
    if ENVIRONMENT not in ("development", "test"):
        raise ValueError(
            f"SECRET_KEY environment variable is required in {ENVIRONMENT}. "
            "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    import secrets
    SECRET_KEY = secrets.token_hex(32)


# ============================================================================
# SENTRY INTEGRATION
# ============================================================================

_sentry_initialized = False

def init_sentry(app: FastAPI = None):
    """Initialize Sentry for error tracking"""
    global _sentry_initialized

    if not SENTRY_DSN:
        logging.info("Sentry DSN not configured - error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            release=RELEASE_VERSION,
            traces_sample_rate=0.1 if ENVIRONMENT == "production" else 1.0,
            profiles_sample_rate=0.1 if ENVIRONMENT == "production" else 1.0,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR
                ),
            ],
            # Don't send PII to Sentry
            send_default_pii=False,
            # Add custom context
            before_send=_sentry_before_send,
        )

        _sentry_initialized = True
        logging.info(f"✅ Sentry initialized for environment: {ENVIRONMENT}")
        return True

    except ImportError:
        logging.warning("sentry-sdk not installed - run: pip install sentry-sdk[fastapi]")
        return False
    except Exception as e:
        logging.error(f"Failed to initialize Sentry: {e}")
        return False


def _sentry_before_send(event, hint):
    """Filter sensitive data before sending to Sentry"""
    # Remove sensitive headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        sensitive_headers = ["authorization", "cookie", "x-api-key"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[REDACTED]"

    # Remove sensitive data from breadcrumbs
    if "breadcrumbs" in event:
        for breadcrumb in event["breadcrumbs"].get("values", []):
            if "data" in breadcrumb:
                for key in list(breadcrumb["data"].keys()):
                    if any(s in key.lower() for s in ["password", "token", "secret", "key"]):
                        breadcrumb["data"][key] = "[REDACTED]"

    return event


def capture_exception(error: Exception, context: Dict[str, Any] = None):
    """Capture exception to Sentry with additional context"""
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    except Exception as e:
        logging.getLogger(__name__).exception(f"Failed to capture exception to Sentry: {e}")


def capture_message(message: str, level: str = "info", context: Dict[str, Any] = None):
    """Capture message to Sentry"""
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logging.getLogger(__name__).exception(f"Failed to capture message to Sentry: {e}")


# ============================================================================
# STRUCTURED LOGGING
# ============================================================================

class StructuredLogger:
    """JSON-formatted logger for production log aggregation"""

    def __init__(self, name: str = "mortgage-crm"):
        self.name = name
        self.logger = logging.getLogger(name)

        # Only configure if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)

            # Use JSON format in production, human-readable in development
            if ENVIRONMENT == "production":
                handler.setFormatter(JSONLogFormatter())
            else:
                handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s'
                ))

            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG if ENVIRONMENT == "development" else logging.INFO)

    def _log(self, level: str, message: str, **kwargs):
        """Internal logging method with structured data"""
        extra = {
            "structured_data": {
                "environment": ENVIRONMENT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs
            }
        }

        getattr(self.logger, level)(message, extra=extra)

    def debug(self, message: str, **kwargs):
        self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("warning", message, **kwargs)

    def error(self, message: str, error: Exception = None, **kwargs):
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
            kwargs["traceback"] = traceback.format_exc()
            capture_exception(error, kwargs)
        self._log("error", message, **kwargs)

    def critical(self, message: str, error: Exception = None, **kwargs):
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
            kwargs["traceback"] = traceback.format_exc()
            capture_exception(error, kwargs)
        self._log("critical", message, **kwargs)


class JSONLogFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add structured data if present
        if hasattr(record, "structured_data"):
            log_data.update(record.structured_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }

        return json.dumps(log_data)


# Global structured logger instance
structured_logger = StructuredLogger()


# ============================================================================
# REQUEST ID TRACING
# ============================================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to all requests for distributed tracing"""

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Add to Sentry scope if initialized
        if _sentry_initialized:
            try:
                import sentry_sdk
                sentry_sdk.set_tag("request_id", request_id)
            except Exception as e:
                logging.getLogger(__name__).exception(f"Failed to set Sentry request_id tag: {e}")

        # Process request
        start_time = time.time()

        try:
            response = await call_next(request)

            # Log request completion
            duration_ms = (time.time() - start_time) * 1000
            structured_logger.info(
                f"{request.method} {request.url.path}",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=request.client.host if request.client else None
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            structured_logger.error(
                f"Request failed: {request.method} {request.url.path}",
                error=e,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2)
            )
            raise


def get_request_id(request: Request) -> str:
    """Get request ID from request state"""
    return getattr(request.state, "request_id", "unknown")


# ============================================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================================

def _get_cors_headers(request: Request) -> dict:
    """Get CORS headers for the request origin."""
    origin = request.headers.get("origin", "")
    headers = {}

    # Add CORS headers if origin is from allowed domains
    if origin and (
        origin.endswith("perenniaai.com") or
        "localhost" in origin or
        origin.endswith(".railway.app") or
        origin.endswith(".vercel.app")
    ):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"

    return headers


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions with proper logging and response"""
    request_id = get_request_id(request)

    # Log the error
    structured_logger.error(
        "Unhandled exception",
        error=exc,
        request_id=request_id,
        method=request.method,
        path=request.url.path
    )

    # Get CORS headers for cross-origin error responses
    cors_headers = _get_cors_headers(request)

    # Determine error response based on environment
    if ENVIRONMENT == "production":
        # Don't expose internal errors in production
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request_id,
                "message": "An unexpected error occurred. Please try again later."
            },
            headers=cors_headers
        )
    else:
        # Include details in development
        return JSONResponse(
            status_code=500,
            content={
                "error": type(exc).__name__,
                "request_id": request_id,
                "message": str(exc)
            },
            headers=cors_headers
        )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with request ID and CORS headers"""
    request_id = get_request_id(request)

    # Log 4xx and 5xx errors
    if exc.status_code >= 400:
        log_level = "warning" if exc.status_code < 500 else "error"
        getattr(structured_logger, log_level)(
            f"HTTP {exc.status_code}: {exc.detail}",
            request_id=request_id,
            status_code=exc.status_code,
            method=request.method,
            path=request.url.path
        )

    # Get CORS headers for cross-origin error responses
    cors_headers = _get_cors_headers(request)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "request_id": request_id,
            "status_code": exc.status_code
        },
        headers=cors_headers
    )


# ============================================================================
# HEALTH CHECK UTILITIES
# ============================================================================

class HealthChecker:
    """Comprehensive health check for all dependencies"""

    def __init__(self):
        self.checks = {}

    def register_check(self, name: str, check_func: Callable):
        """Register a health check function"""
        self.checks[name] = check_func

    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks and return status"""
        results = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": ENVIRONMENT,
            "checks": {}
        }

        overall_healthy = True

        for name, check_func in self.checks.items():
            try:
                start = time.time()
                is_healthy = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                duration_ms = (time.time() - start) * 1000

                results["checks"][name] = {
                    "status": "healthy" if is_healthy else "unhealthy",
                    "duration_ms": round(duration_ms, 2)
                }

                if not is_healthy:
                    overall_healthy = False

            except Exception as e:
                results["checks"][name] = {
                    "status": "unhealthy",
                    "error": "Internal server error"
                }
                overall_healthy = False

        results["status"] = "healthy" if overall_healthy else "unhealthy"
        return results

    async def check_readiness(self) -> bool:
        """Quick readiness check - can accept traffic?"""
        results = await self.check_all()
        return results["status"] == "healthy"

    def check_liveness(self) -> bool:
        """Liveness check - is process alive?"""
        return True


# Import asyncio for health checker
import asyncio

# Global health checker instance
health_checker = HealthChecker()


# ============================================================================
# PERFORMANCE MONITORING DECORATOR
# ============================================================================

def monitor_performance(operation_name: str = None, warn_threshold_ms: float = 1000):
    """Decorator to monitor endpoint/function performance"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                if duration_ms > warn_threshold_ms:
                    structured_logger.warning(
                        f"Slow operation: {op_name}",
                        operation=op_name,
                        duration_ms=round(duration_ms, 2),
                        threshold_ms=warn_threshold_ms
                    )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                structured_logger.error(
                    f"Operation failed: {op_name}",
                    error=e,
                    operation=op_name,
                    duration_ms=round(duration_ms, 2)
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                if duration_ms > warn_threshold_ms:
                    structured_logger.warning(
                        f"Slow operation: {op_name}",
                        operation=op_name,
                        duration_ms=round(duration_ms, 2),
                        threshold_ms=warn_threshold_ms
                    )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                structured_logger.error(
                    f"Operation failed: {op_name}",
                    error=e,
                    operation=op_name,
                    duration_ms=round(duration_ms, 2)
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# DATABASE QUERY MONITORING
# ============================================================================

def setup_query_logging(engine):
    """Set up slow query logging for SQLAlchemy"""
    from sqlalchemy import event

    SLOW_QUERY_THRESHOLD_MS = float(os.getenv("SLOW_QUERY_THRESHOLD_MS", "500"))

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.time())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total_time = time.time() - conn.info["query_start_time"].pop(-1)
        total_time_ms = total_time * 1000

        if total_time_ms > SLOW_QUERY_THRESHOLD_MS:
            structured_logger.warning(
                "Slow database query detected",
                duration_ms=round(total_time_ms, 2),
                threshold_ms=SLOW_QUERY_THRESHOLD_MS,
                query=statement[:500],  # Truncate long queries
                parameters=str(parameters)[:200] if parameters else None
            )


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

_shutdown_handlers = []

def register_shutdown_handler(handler: Callable):
    """Register a function to be called on shutdown"""
    _shutdown_handlers.append(handler)


async def graceful_shutdown():
    """Execute all shutdown handlers"""
    structured_logger.info("Initiating graceful shutdown...")

    for handler in _shutdown_handlers:
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
        except Exception as e:
            structured_logger.error(f"Shutdown handler failed", error=e)

    structured_logger.info("Graceful shutdown complete")


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_production_hardening(app: FastAPI, engine=None):
    """
    One-call setup for all production hardening features.

    Usage in main.py:
        from production_hardening import setup_production_hardening
        setup_production_hardening(app, engine)
    """
    # Initialize Sentry
    init_sentry(app)

    # Add request ID middleware
    app.add_middleware(RequestIDMiddleware)

    # Add exception handlers
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Setup query logging if engine provided
    if engine:
        setup_query_logging(engine)

    # Register shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        await graceful_shutdown()

    structured_logger.info(
        "Production hardening initialized",
        environment=ENVIRONMENT,
        sentry_enabled=_sentry_initialized
    )

    return {
        "sentry_enabled": _sentry_initialized,
        "environment": ENVIRONMENT,
        "structured_logging": True,
        "request_tracing": True,
        "query_monitoring": engine is not None
    }
