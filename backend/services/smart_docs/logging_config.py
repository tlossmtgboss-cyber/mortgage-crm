"""
Smart Docs V2 Structured Logging

Provides trace-aware, structured logging for all Smart Docs services.
Each log entry includes trace_id, org_id, loan_id, user_id, service name,
and any additional context -- formatted as JSON for DataDog/Splunk ingestion.

Usage:
    from services.smart_docs.logging_config import get_smart_docs_logger

    logger = get_smart_docs_logger("ai_classifier")
    ctx = logger.with_context(org_id=5, loan_id=100, user_id=42)
    ctx.info("Classification started", doc_type="paystub")

    with ctx.timed("classify_document"):
        result = do_classification()

    ctx.log_ai_call(
        operation="classify",
        model="claude-sonnet-4-6",
        tokens_in=500,
        tokens_out=120,
        duration_ms=1234.5,
        cost_estimate=0.0045,
        success=True,
    )
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Optional

# ---------------------------------------------------------------------------
# Trace ID propagation via contextvars
# ---------------------------------------------------------------------------

_trace_id_var: ContextVar[Optional[str]] = ContextVar("smart_docs_trace_id", default=None)

TRACE_ID_HEADER = "X-Trace-ID"


def generate_trace_id() -> str:
    """Generate a UUID-based trace ID."""
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """Retrieve current trace ID from contextvars, or generate one."""
    tid = _trace_id_var.get()
    if tid is None:
        tid = generate_trace_id()
        _trace_id_var.set(tid)
    return tid


def set_trace_id(trace_id: str) -> None:
    """Set the current trace ID in contextvars."""
    _trace_id_var.set(trace_id)


# ---------------------------------------------------------------------------
# PII patterns -- lightweight check so we never embed raw PII in structured
# log fields.  The middleware.pii_log_filter.PIIRedactionFilter handles
# message-level scrubbing; this guards against extra-field leakage.
# ---------------------------------------------------------------------------

import re

_PII_PATTERNS = [
    re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),             # SSN
    re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),  # Credit card
    re.compile(r"\baccount[_\s#:]*\d{8,17}\b", re.IGNORECASE),   # Bank account
]


def _scrub_value(value: Any) -> Any:
    """Redact PII from a single value before it enters a log record."""
    if not isinstance(value, str):
        return value
    for pat in _PII_PATTERNS:
        if pat.search(value):
            return "[PII_REDACTED]"
    return value


def _scrub_extras(extras: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy with PII-bearing values replaced."""
    return {k: _scrub_value(v) for k, v in extras.items()}


# ---------------------------------------------------------------------------
# JSON Formatter (DataDog / Splunk compatible)
# ---------------------------------------------------------------------------

class SmartDocsJsonFormatter(logging.Formatter):
    """
    Format log records as single-line JSON objects.

    Output example:
        {"timestamp": "2026-03-12T...", "level": "INFO", "service": "ai_classifier",
         "trace_id": "abc123", "org_id": 5, "message": "Classification complete",
         "doc_type": "PAYSTUB", "confidence": 0.95, "duration_ms": 1234}
    """

    # Standard LogRecord attrs we exclude from extra-field passthrough
    _BUILTIN_ATTRS = frozenset({
        "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "getMessage",
        "exc_info", "exc_text", "stack_info", "name", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", record.name),
            "trace_id": getattr(record, "trace_id", get_trace_id()),
            "message": record.getMessage(),
        }

        # Merge structured extra fields
        for key, value in record.__dict__.items():
            if key in self._BUILTIN_ATTRS or key.startswith("_"):
                continue
            if key in log_obj:
                continue
            if isinstance(value, (datetime,)):
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
# ContextLogger -- carries bound context across all log calls
# ---------------------------------------------------------------------------

class ContextLogger:
    """
    Logger with bound context (trace_id, org_id, loan_id, user_id, service).

    Every call to info/warning/error/exception merges bound context into the
    ``extra`` dict so structured formatters can pick it up.
    """

    def __init__(
        self,
        logger: logging.Logger,
        service_name: str,
        trace_id: Optional[str] = None,
        org_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        user_id: Optional[int] = None,
        **extra_context: Any,
    ):
        self._logger = logger
        self._context: Dict[str, Any] = {
            "service": service_name,
            "trace_id": trace_id or get_trace_id(),
        }
        if org_id is not None:
            self._context["org_id"] = org_id
        if loan_id is not None:
            self._context["loan_id"] = loan_id
        if user_id is not None:
            self._context["user_id"] = user_id
        if extra_context:
            self._context.update(extra_context)

    # -- core log methods ---------------------------------------------------

    def _log(self, level: int, msg: str, exc_info: Any = None, **extra: Any) -> None:
        merged = {**self._context, **_scrub_extras(extra)}
        self._logger.log(level, msg, extra=merged, exc_info=exc_info)

    def info(self, msg: str, **extra: Any) -> None:
        self._log(logging.INFO, msg, **extra)

    def warning(self, msg: str, **extra: Any) -> None:
        self._log(logging.WARNING, msg, **extra)

    def error(self, msg: str, **extra: Any) -> None:
        self._log(logging.ERROR, msg, **extra)

    def exception(self, msg: str, **extra: Any) -> None:
        self._log(logging.ERROR, msg, exc_info=True, **extra)

    def debug(self, msg: str, **extra: Any) -> None:
        self._log(logging.DEBUG, msg, **extra)

    # -- structured helpers -------------------------------------------------

    @contextmanager
    def timed(self, operation: str) -> Generator[None, None, None]:
        """
        Context manager that logs operation start/end with duration_ms.

        Usage:
            with ctx.timed("classify_document"):
                result = classifier.run(...)
        """
        self.info(f"{operation} started", event_type="operation_start", operation=operation)
        start = time.monotonic()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            level = logging.INFO if success else logging.ERROR
            self._log(
                level,
                f"{operation} {'completed' if success else 'failed'}",
                event_type="operation_end",
                operation=operation,
                duration_ms=duration_ms,
                success=success,
            )

    def log_ai_call(
        self,
        operation: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: float,
        cost_estimate: Optional[float] = None,
        success: bool = True,
        **extra: Any,
    ) -> None:
        """
        Log a structured AI/LLM API call.

        Enables tracking of token usage, latency, and cost across all
        Smart Docs AI services (classifier, reviewer, fraud, OCR, etc.).
        """
        self._log(
            logging.INFO if success else logging.ERROR,
            f"AI call: {operation}",
            event_type="ai_call",
            operation=operation,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            total_tokens=tokens_in + tokens_out,
            duration_ms=round(duration_ms, 2),
            cost_estimate=round(cost_estimate, 6) if cost_estimate is not None else None,
            success=success,
            **extra,
        )

    def log_decision(
        self,
        decision_type: str,
        entity_id: Any,
        decision: str,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """
        Log a structured decision event (classification, approval, fraud flag, etc.).
        """
        self._log(
            logging.INFO,
            f"Decision: {decision_type}={decision}",
            event_type="decision",
            decision_type=decision_type,
            entity_id=str(entity_id),
            decision=decision,
            confidence=round(confidence, 4) if confidence is not None else None,
            reasoning=reasoning,
            **extra,
        )

    def log_security_event(
        self,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> None:
        """
        Log a security-relevant event (access denied, suspicious upload, etc.).
        """
        merged_details = _scrub_extras(details or {})
        self._log(
            logging.WARNING,
            f"Security event: {event_type}",
            event_type="security_event",
            security_event_type=event_type,
            **merged_details,
            **extra,
        )


# ---------------------------------------------------------------------------
# SmartDocsLogger -- top-level factory per service
# ---------------------------------------------------------------------------

class SmartDocsLogger:
    """
    Structured logger factory for a Smart Docs service.

    Usage:
        logger = SmartDocsLogger("ai_classifier")
        ctx = logger.with_context(org_id=5, loan_id=100)
        ctx.info("ready")
    """

    # Class-level flag: True once the JSON handler has been attached
    _handler_installed: bool = False

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._logger = logging.getLogger(f"smart_docs.{service_name}")
        self._logger.setLevel(logging.DEBUG)

        # Install JSON handler once per process
        if not SmartDocsLogger._handler_installed:
            self._install_handler()
            SmartDocsLogger._handler_installed = True

    @staticmethod
    def _install_handler() -> None:
        """Attach SmartDocsJsonFormatter to the smart_docs logger hierarchy."""
        parent = logging.getLogger("smart_docs")
        parent.setLevel(logging.DEBUG)
        # Avoid duplicate handlers
        if not any(
            isinstance(h.formatter, SmartDocsJsonFormatter)
            for h in parent.handlers
        ):
            handler = logging.StreamHandler()
            handler.setFormatter(SmartDocsJsonFormatter())
            parent.addHandler(handler)
            parent.propagate = False  # Don't double-log via root

    def with_context(
        self,
        trace_id: Optional[str] = None,
        org_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        user_id: Optional[int] = None,
        **extra: Any,
    ) -> ContextLogger:
        """Return a ContextLogger bound to the given identifiers."""
        return ContextLogger(
            logger=self._logger,
            service_name=self.service_name,
            trace_id=trace_id,
            org_id=org_id,
            loan_id=loan_id,
            user_id=user_id,
            **extra,
        )

    # Convenience: allow direct logging without context binding
    def info(self, msg: str, **extra: Any) -> None:
        self.with_context().info(msg, **extra)

    def warning(self, msg: str, **extra: Any) -> None:
        self.with_context().warning(msg, **extra)

    def error(self, msg: str, **extra: Any) -> None:
        self.with_context().error(msg, **extra)

    def exception(self, msg: str, **extra: Any) -> None:
        self.with_context().exception(msg, **extra)


# ---------------------------------------------------------------------------
# Module-level factory (preferred import point)
# ---------------------------------------------------------------------------

def get_smart_docs_logger(service_name: str) -> SmartDocsLogger:
    """
    Factory function returning a SmartDocsLogger for the given service.

    Usage:
        from services.smart_docs.logging_config import get_smart_docs_logger
        logger = get_smart_docs_logger("fraud_detection")
    """
    return SmartDocsLogger(service_name)
