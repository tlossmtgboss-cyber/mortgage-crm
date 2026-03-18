"""
Perennia AI - Structured Logging Configuration

Provides production-grade structured logging with automatic request
correlation ID injection.

Features:
- StructuredJsonFormatter: JSON output with timestamp, level, message,
  request_id, user_id, org_id, path, method, duration_ms
- HumanReadableFormatter: Colored, readable output for local development
- RequestContextFilter: Injects request context from contextvars into
  every log record automatically
- configure_logging(): One-call setup for the root logger
- get_logger(name): Convenience function returning a properly-configured logger

Environment detection:
- Production (RAILWAY_ENVIRONMENT or ENVIRONMENT=production): JSON output
- Development (default): Human-readable output

Usage:
    # At app startup (main.py):
    from utils.logging_config import configure_logging
    configure_logging()

    # In any module:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Loan created", extra={"loan_id": 42, "amount": 350000})
"""

from __future__ import annotations

import json
import logging
import os
import traceback as _tb
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# RequestContextFilter -- injects correlation ID and user context
# ---------------------------------------------------------------------------

class RequestContextFilter(logging.Filter):
    """
    Logging filter that reads request-scoped context from contextvars
    (set by middleware.request_context.RequestContextMiddleware) and
    attaches it to every log record.

    Fields injected:
    - request_id: correlation ID from X-Request-ID header or auto-generated
    - user_id: authenticated user ID (if available)
    - org_id: tenant organization ID (if available)
    - method: HTTP method (if available)
    - path: request path (if available)

    These fields are available to any Formatter via record attributes.
    If the extra={} dict already provides a value, it is not overwritten.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Lazy import to avoid circular imports at module load time.
        # The middleware module is lightweight and only uses stdlib.
        try:
            from middleware.request_context import (
                get_request_id,
                get_user_id,
                get_org_id,
                get_request_method,
                get_request_path,
            )
        except ImportError:
            # If middleware hasn't been installed yet, just pass through
            return True

        _set_if_missing(record, "request_id", get_request_id)
        _set_if_missing(record, "user_id", get_user_id)
        _set_if_missing(record, "org_id", get_org_id)
        _set_if_missing(record, "method", get_request_method)
        _set_if_missing(record, "path", get_request_path)
        return True


def _set_if_missing(record: logging.LogRecord, attr: str, getter) -> None:
    """Set a record attribute from a getter function if not already present."""
    current = getattr(record, attr, None)
    if current is None:
        try:
            value = getter()
            setattr(record, attr, value)
        except Exception:
            setattr(record, attr, None)


# ---------------------------------------------------------------------------
# StructuredJsonFormatter -- production JSON output
# ---------------------------------------------------------------------------

class StructuredJsonFormatter(logging.Formatter):
    """
    Formats each log record as a single-line JSON object.

    Standard fields on every line:
    - timestamp: ISO 8601 in UTC
    - level: DEBUG / INFO / WARNING / ERROR / CRITICAL
    - logger: logger name (e.g. "routes.scheduler.appointments")
    - message: formatted log message
    - module: Python module name
    - function: function name
    - line: line number

    Context fields (when available via RequestContextFilter):
    - request_id, user_id, org_id, method, path

    Additional fields passed via extra={} are merged into the output.

    Example:
        {"timestamp":"2026-03-18T10:00:00+00:00","level":"INFO",
         "logger":"routes.loans","message":"Loan created",
         "request_id":"a1b2c3","user_id":"5","org_id":"1",
         "method":"POST","path":"/api/v1/loans","loan_id":42}
    """

    # Standard LogRecord attributes excluded from extra-field passthrough
    _BUILTIN_ATTRS = frozenset({
        "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "getMessage",
        "exc_info", "exc_text", "stack_info", "name", "taskName",
    })

    # Context fields injected by RequestContextFilter
    _CONTEXT_FIELDS = ("request_id", "user_id", "org_id", "method", "path")

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context fields (only when non-None)
        for field in self._CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_obj[field] = value

        # Merge any additional extra fields from extra={}
        for key, value in record.__dict__.items():
            if key in self._BUILTIN_ATTRS or key.startswith("_"):
                continue
            if key in log_obj:
                continue
            if isinstance(value, datetime):
                value = value.isoformat()
            log_obj[key] = value

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": _tb.format_exception(*record.exc_info),
            }

        return json.dumps(log_obj, default=str)


# ---------------------------------------------------------------------------
# HumanReadableFormatter -- development console output
# ---------------------------------------------------------------------------

class HumanReadableFormatter(logging.Formatter):
    """
    Human-friendly log formatter for local development.

    Output format:
        2026-03-18 10:00:00 INFO  [a1b2c3] routes.loans - Loan created {loan_id=42}

    The [request_id] is shown in brackets when available.
    Extra fields are appended as key=value pairs.
    """

    _BUILTIN_ATTRS = StructuredJsonFormatter._BUILTIN_ATTRS
    _CONTEXT_FIELDS = StructuredJsonFormatter._CONTEXT_FIELDS
    # Fields handled explicitly in the format string, not in extras
    _HANDLED_FIELDS = frozenset({
        "request_id", "user_id", "org_id", "method", "path",
        "event_type",
    })

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(8)
        request_id = getattr(record, "request_id", None)
        rid_str = f"[{request_id[:12]}]" if request_id else "[--------]"
        user_id = getattr(record, "user_id", None)
        user_str = f" user={user_id}" if user_id else ""
        org_id = getattr(record, "org_id", None)
        org_str = f" org={org_id}" if org_id else ""

        # Collect extra fields
        extras = {}
        for key, value in record.__dict__.items():
            if key in self._BUILTIN_ATTRS or key.startswith("_"):
                continue
            if key in self._HANDLED_FIELDS:
                continue
            extras[key] = value

        extras_str = ""
        if extras:
            pairs = " ".join(f"{k}={v}" for k, v in extras.items())
            extras_str = f" {{{pairs}}}"

        msg = record.getMessage()
        line = f"{ts} {level} {rid_str}{user_str}{org_str} {record.name} - {msg}{extras_str}"

        if record.exc_info and record.exc_info[0] is not None:
            line += "\n" + "".join(_tb.format_exception(*record.exc_info))

        return line


# ---------------------------------------------------------------------------
# configure_logging -- call once at app startup
# ---------------------------------------------------------------------------

_configured = False


def configure_logging(log_level: Optional[str] = None) -> None:
    """
    Configure the Python root logger with structured output.

    In production (RAILWAY_ENVIRONMENT or ENVIRONMENT=production):
      - JSON formatter (StructuredJsonFormatter) for machine parsing
    In development:
      - Human-readable formatter (HumanReadableFormatter) for console

    RequestContextFilter is installed on the root logger so ALL loggers
    automatically get request_id, user_id, org_id injected.

    Args:
        log_level: Override log level. Defaults to LOG_LEVEL env var,
                   or WARNING in production, INFO in development.
    """
    global _configured
    if _configured:
        return
    _configured = True

    is_production = bool(
        os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") == "production"
    )

    # Determine console log level
    if log_level:
        level = getattr(logging, log_level.upper(), logging.INFO)
    elif os.getenv("LOG_LEVEL"):
        level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    elif is_production:
        level = logging.WARNING
    else:
        level = logging.INFO

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Let handlers decide what to show

    # Install RequestContextFilter on root (idempotent)
    if not any(isinstance(f, RequestContextFilter) for f in root.filters):
        root.addFilter(RequestContextFilter())

    # Choose formatter based on environment
    if is_production:
        formatter = StructuredJsonFormatter()
    else:
        formatter = HumanReadableFormatter()

    # Replace existing StreamHandlers with our formatted one.
    # Keep FileHandlers and other handler types untouched.
    for handler in root.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # File handler (JSON) -- only if LOG_FILE env var is set
    log_file = os.getenv("LOG_FILE")
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(StructuredJsonFormatter())
            root.addHandler(file_handler)
        except OSError as e:
            root.warning(f"Could not set up file logging at {log_file}: {e}")

    # Quiet down noisy third-party loggers
    for noisy in (
        "urllib3", "httpcore", "httpx", "sqlalchemy.engine",
        "watchfiles", "apscheduler", "apscheduler.scheduler",
        "apscheduler.executors", "uvicorn.access",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# get_logger -- convenience factory
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that participates in the structured logging system.

    The returned logger inherits the root logger's handlers and filters,
    including RequestContextFilter, so request_id/user_id/org_id are
    automatically included in every log record.

    Usage:
        from utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened", extra={"loan_id": 42})
    """
    return logging.getLogger(name)
