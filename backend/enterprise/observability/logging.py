"""
Structured Logging Service

Provides JSON-formatted structured logging for:
- Log aggregation (ELK, Datadog, etc.)
- Trace correlation
- Context preservation
- Log level management

Enterprise Features:
- JSON structured output
- Trace ID correlation
- Request context binding
- Sensitive data redaction
- Log shipping to external services
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from enum import Enum
import re

# Context variables for log enrichment
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_user_id: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_organization_id: ContextVar[Optional[str]] = ContextVar('org_id', default=None)
_extra_context: ContextVar[Dict[str, Any]] = ContextVar('extra_context', default={})


class LogLevel(str, Enum):
    """Standard log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogRecord:
    """Structured log record"""
    timestamp: str
    level: str
    message: str
    logger_name: str

    # Tracing
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    request_id: Optional[str] = None

    # Context
    user_id: Optional[str] = None
    organization_id: Optional[str] = None

    # Error details
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    # Extra data
    extra: Dict[str, Any] = field(default_factory=dict)

    # Service info
    service: str = "mortgage-crm"
    environment: str = "development"
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)


class SensitiveDataRedactor:
    """Redact sensitive data from log messages and extra data"""

    # Patterns for sensitive data
    PATTERNS = [
        (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '***-**-****'),  # SSN
        (re.compile(r'\b\d{9}\b'), '*********'),  # SSN without dashes
        (re.compile(r'\b\d{16}\b'), '****************'),  # Credit card
        (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), '****-****-****-****'),
        (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.I), 'password=***'),
        (re.compile(r'secret["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.I), 'secret=***'),
        (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.I), 'api_key=***'),
        (re.compile(r'token["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.I), 'token=***'),
        (re.compile(r'bearer\s+[a-zA-Z0-9\-_.]+', re.I), 'Bearer ***'),
    ]

    # Fields to always redact
    SENSITIVE_FIELDS = {
        'password', 'secret', 'token', 'api_key', 'apikey', 'auth',
        'ssn', 'social_security', 'credit_card', 'card_number',
        'cvv', 'pin', 'bank_account', 'routing_number',
    }

    @classmethod
    def redact_string(cls, text: str) -> str:
        """Redact sensitive patterns from a string"""
        for pattern, replacement in cls.PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive fields from a dictionary"""
        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Check if key is sensitive
            if any(s in key_lower for s in cls.SENSITIVE_FIELDS):
                result[key] = '***REDACTED***'
            elif isinstance(value, dict):
                result[key] = cls.redact_dict(value)
            elif isinstance(value, str):
                result[key] = cls.redact_string(value)
            else:
                result[key] = value

        return result


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""

    def __init__(
        self,
        service_name: str = "mortgage-crm",
        environment: str = "development",
        version: str = "1.0.0",
        redact_sensitive: bool = True,
    ):
        super().__init__()
        self.service_name = service_name
        self.environment = environment
        self.version = version
        self.redact_sensitive = redact_sensitive

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Get trace context
        from .tracing import get_current_trace_id, get_current_span_id
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()

        # Build structured record
        log_record = LogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
            trace_id=trace_id,
            span_id=span_id,
            request_id=_request_id.get(),
            user_id=_user_id.get(),
            organization_id=_organization_id.get(),
            service=self.service_name,
            environment=self.environment,
            version=self.version,
        )

        # Add error info if present
        if record.exc_info:
            log_record.error_type = record.exc_info[0].__name__ if record.exc_info[0] else None
            log_record.error_message = str(record.exc_info[1]) if record.exc_info[1] else None
            log_record.stack_trace = ''.join(traceback.format_exception(*record.exc_info))

        # Add extra context
        extra = getattr(record, 'extra', {}) or {}
        extra.update(_extra_context.get() or {})

        if extra:
            if self.redact_sensitive:
                extra = SensitiveDataRedactor.redact_dict(extra)
            log_record.extra = extra

        # Redact message if needed
        if self.redact_sensitive:
            log_record.message = SensitiveDataRedactor.redact_string(log_record.message)

        return log_record.to_json()


class StructuredLogger:
    """
    Structured logger with context binding support.

    Usage:
        logger = StructuredLogger("my_module")
        logger.info("Processing loan", loan_id="123", amount=500000)

        with logger.bind(user_id="456"):
            logger.info("User action")  # Automatically includes user_id
    """

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
    ):
        self._logger = logging.getLogger(name)
        self._bound_context: Dict[str, Any] = {}

    def _log(
        self,
        level: int,
        message: str,
        exc_info: bool = False,
        **kwargs,
    ):
        """Internal log method"""
        # Merge bound context with kwargs
        extra = {**self._bound_context, **kwargs}

        self._logger.log(
            level,
            message,
            exc_info=exc_info,
            extra={"extra": extra},
        )

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = True, **kwargs):
        """Log error message"""
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Log critical message"""
        self._log(logging.CRITICAL, message, exc_info=exc_info, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with traceback"""
        self._log(logging.ERROR, message, exc_info=True, **kwargs)

    def bind(self, **kwargs) -> "BoundLogger":
        """Create a bound logger with additional context"""
        return BoundLogger(self, kwargs)


class BoundLogger:
    """Logger with bound context (context manager)"""

    def __init__(self, parent: StructuredLogger, context: Dict[str, Any]):
        self._parent = parent
        self._context = context
        self._previous_context: Dict[str, Any] = {}

    def __enter__(self) -> StructuredLogger:
        self._previous_context = self._parent._bound_context.copy()
        self._parent._bound_context.update(self._context)
        return self._parent

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._parent._bound_context = self._previous_context


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",  # json or text
    service_name: str = "mortgage-crm",
    environment: Optional[str] = None,
    version: Optional[str] = None,
) -> None:
    """
    Setup application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format (json or text)
        service_name: Service name for logs
        environment: Environment name
        version: Application version
    """
    environment = environment or os.getenv("ENVIRONMENT", "development")
    version = version or os.getenv("VERSION", "1.0.0")

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    # Set formatter
    if format_type == "json":
        formatter = JsonFormatter(
            service_name=service_name,
            environment=environment,
            version=version,
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Log initialization
    root_logger.info(
        f"Logging initialized",
        extra={"extra": {
            "format": format_type,
            "level": level,
            "service": service_name,
            "environment": environment,
        }}
    )


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger by name"""
    return StructuredLogger(name)


# Context management functions
def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    **extra,
):
    """Set the current request context for logging"""
    if request_id:
        _request_id.set(request_id)
    if user_id:
        _user_id.set(user_id)
    if organization_id:
        _organization_id.set(organization_id)
    if extra:
        current = _extra_context.get() or {}
        current.update(extra)
        _extra_context.set(current)


def clear_request_context():
    """Clear the current request context"""
    _request_id.set(None)
    _user_id.set(None)
    _organization_id.set(None)
    _extra_context.set({})


# FastAPI middleware for request logging
class LoggingMiddleware:
    """
    FastAPI middleware for request/response logging.

    Usage:
        from fastapi import FastAPI
        from enterprise.observability.logging import LoggingMiddleware

        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
    """

    def __init__(
        self,
        app,
        logger_name: str = "http",
        log_request_body: bool = False,
        log_response_body: bool = False,
    ):
        self.app = app
        self.logger = get_logger(logger_name)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import uuid
        import time

        # Generate request ID
        request_id = str(uuid.uuid4())

        # Extract request info
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        headers = dict(scope.get("headers", []))
        headers = {k.decode(): v.decode() for k, v in headers.items() if isinstance(k, bytes)}

        # Set request context
        set_request_context(
            request_id=request_id,
            path=path,
            method=method,
        )

        # Log request
        start_time = time.time()
        self.logger.info(
            f"Request started: {method} {path}",
            request_id=request_id,
            method=method,
            path=path,
            user_agent=headers.get("user-agent", ""),
            content_length=headers.get("content-length", "0"),
        )

        # Track response
        status_code = 500
        response_headers = {}

        async def send_wrapper(message):
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                response_headers = dict(message.get("headers", []))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.logger.error(
                f"Request failed: {method} {path}",
                request_id=request_id,
                error=str(e),
            )
            raise
        finally:
            # Log response
            duration_ms = (time.time() - start_time) * 1000
            log_method = self.logger.info if status_code < 400 else self.logger.warning

            log_method(
                f"Request completed: {method} {path} - {status_code}",
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Clear context
            clear_request_context()
