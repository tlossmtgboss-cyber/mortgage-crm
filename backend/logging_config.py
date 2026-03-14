"""
Perennia AI - Platform-Wide Structured Logging Configuration

Provides JSON-formatted structured logging for all backend services.
Integrates with the existing Smart Docs logging (services/smart_docs/logging_config.py)
and chat logging (middleware/structured_logging.py) without replacing them.

Features:
- StructuredFormatter: JSON-per-line output with standard fields
- RequestContextFilter: Injects request_id, user_id, org_id from contextvars
- configure_logging(app): Sets up root logger with file + console handlers
- Separate log levels for file (DEBUG) vs console (INFO)

Usage:
    from logging_config import configure_logging
    configure_logging(app)

    # Then in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Something happened", extra={"loan_id": 42})
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Context variables for request-scoped data
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id_var: ContextVar[Optional[int]] = ContextVar("ctx_user_id", default=None)
_org_id_var: ContextVar[Optional[int]] = ContextVar("ctx_org_id", default=None)
_endpoint_var: ContextVar[Optional[str]] = ContextVar("ctx_endpoint", default=None)


def get_request_id() -> Optional[str]:
    """Retrieve current request ID from context."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set current request ID in context."""
    _request_id_var.set(request_id)


def generate_request_id() -> str:
    """Generate a new UUID-based request ID."""
    return uuid.uuid4().hex


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[int] = None,
    org_id: Optional[int] = None,
    endpoint: Optional[str] = None,
) -> None:
    """Set all request context variables at once."""
    if request_id is not None:
        _request_id_var.set(request_id)
    if user_id is not None:
        _user_id_var.set(user_id)
    if org_id is not None:
        _org_id_var.set(org_id)
    if endpoint is not None:
        _endpoint_var.set(endpoint)


def clear_request_context() -> None:
    """Clear all request context variables."""
    _request_id_var.set(None)
    _user_id_var.set(None)
    _org_id_var.set(None)
    _endpoint_var.set(None)


# ---------------------------------------------------------------------------
# RequestContextFilter -- injects context into every log record
# ---------------------------------------------------------------------------

class RequestContextFilter(logging.Filter):
    """
    Logging filter that adds request-scoped fields to every log record.

    Fields injected:
    - request_id: from X-Request-ID header or auto-generated UUID
    - user_id: authenticated user ID (if available)
    - org_id: tenant organization ID (if available)
    - endpoint: request path (if available)

    These fields are read from contextvars set by the request logging
    middleware at the start of each request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Only set if not already present (allows explicit overrides via extra={})
        if not hasattr(record, "request_id") or record.request_id is None:  # type: ignore[attr-defined]
            record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        if not hasattr(record, "user_id") or record.user_id is None:  # type: ignore[attr-defined]
            record.user_id = _user_id_var.get()  # type: ignore[attr-defined]
        if not hasattr(record, "org_id") or record.org_id is None:  # type: ignore[attr-defined]
            record.org_id = _org_id_var.get()  # type: ignore[attr-defined]
        if not hasattr(record, "endpoint") or record.endpoint is None:  # type: ignore[attr-defined]
            record.endpoint = _endpoint_var.get()  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# StructuredFormatter -- JSON output per line
# ---------------------------------------------------------------------------

class StructuredFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Standard fields emitted on every line:
    - timestamp: ISO 8601 in UTC
    - level: DEBUG / INFO / WARNING / ERROR / CRITICAL
    - logger: logger name (e.g. "routes.scheduler.appointments")
    - message: formatted log message
    - module: Python module name
    - function: function name
    - line: line number

    Context fields (when available via RequestContextFilter):
    - request_id, user_id, org_id, endpoint

    Extra fields passed via extra={} are merged into the output.

    Example output:
        {"timestamp":"2026-03-13T10:00:00+00:00","level":"INFO",
         "logger":"routes.scheduler","message":"Appointment created",
         "module":"appointments","function":"create","line":42,
         "request_id":"abc123","user_id":5,"org_id":1,
         "appointment_id":99,"duration_ms":12.5}
    """

    # LogRecord attributes that are not passed through as extra fields
    _BUILTIN_ATTRS = frozenset({
        "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "getMessage",
        "exc_info", "exc_text", "stack_info", "name", "taskName",
    })

    # Context fields injected by RequestContextFilter -- included in output
    # only when non-None
    _CONTEXT_FIELDS = frozenset({
        "request_id", "user_id", "org_id", "endpoint",
    })

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

        # Add context fields if present and non-None
        for field in self._CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_obj[field] = value

        # Add duration_ms if present (commonly set by middleware/timed ops)
        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            log_obj["duration_ms"] = duration_ms

        # Merge any additional extra fields
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
            import traceback as _tb
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": _tb.format_exception(*record.exc_info),
            }

        return json.dumps(log_obj, default=str)


# ---------------------------------------------------------------------------
# configure_logging -- app startup entry point
# ---------------------------------------------------------------------------

_configured = False


def configure_logging(app=None, log_level: str = None) -> None:
    """
    Configure the root logger with StructuredFormatter and RequestContextFilter.

    Sets up two handlers:
    - Console (stderr): Outputs JSON at INFO level (or LOG_LEVEL env var)
    - File (logs/perennia.log): Outputs JSON at DEBUG level when LOG_FILE
      env var is set or logs/ directory exists

    Call once during app startup. Safe to call multiple times (idempotent).

    Args:
        app: FastAPI app instance (unused currently, reserved for future
             middleware auto-registration)
        log_level: Override log level for console. Defaults to LOG_LEVEL
                   env var or "INFO".
    """
    global _configured
    if _configured:
        return
    _configured = True

    console_level = getattr(
        logging,
        (log_level or os.getenv("LOG_LEVEL", "INFO")).upper(),
        logging.INFO,
    )
    file_level = logging.DEBUG

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Allow all through; handlers filter by level

    # Install context filter on root so all loggers get request context
    context_filter = RequestContextFilter()
    if not any(isinstance(f, RequestContextFilter) for f in root.filters):
        root.addFilter(context_filter)

    formatter = StructuredFormatter()

    # --- Console handler (JSON to stderr) ---
    # Check if we already have a StructuredFormatter console handler
    has_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        and isinstance(h.formatter, StructuredFormatter)
        for h in root.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # --- File handler (JSON to file at DEBUG level) ---
    log_file = os.getenv("LOG_FILE")
    if not log_file:
        # Auto-detect: use logs/perennia.log if logs/ dir exists
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if os.path.isdir(log_dir):
            log_file = os.path.join(log_dir, "perennia.log")

    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            has_file = any(
                isinstance(h, logging.FileHandler)
                and isinstance(h.formatter, StructuredFormatter)
                for h in root.handlers
            )
            if not has_file:
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setLevel(file_level)
                file_handler.setFormatter(formatter)
                root.addHandler(file_handler)
        except OSError as e:
            # If we can't write to the log file, just warn on console
            root.warning(f"Could not set up file logging at {log_file}: {e}")

    # Quiet down noisy third-party loggers
    for noisy in ("urllib3", "httpcore", "httpx", "sqlalchemy.engine", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
