"""
Structured Logging Middleware  [PARTIALLY DEPRECATED 2026-04-30]

The RequestLoggingMiddleware class in this file is superseded by
middleware/request_context.py (RequestContextMiddleware) and should NOT be
registered as middleware.  However, the StructuredLogger utility class and its
domain-specific log methods (log_chat_interaction, log_cta_event, log_call_event,
etc.) remain in active use by chat_system_bootstrap.py and chat_state_routes.py.

Provides production-grade logging for:
- Chat interactions with full context
- CTA events for conversion tracking
- Call events for telephony monitoring
- Errors with stack traces
- Performance metrics

Output format is JSON for easy parsing by:
- CloudWatch Logs
- DataDog
- Splunk
- ELK Stack
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class JsonFormatter(logging.Formatter):
    """Format logs as JSON for structured logging systems"""

    EXCLUDED_ATTRS = {
        'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
        'thread', 'threadName', 'processName', 'process', 'getMessage',
        'exc_info', 'exc_text', 'stack_info', 'name'
    }

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in self.EXCLUDED_ATTRS and not key.startswith('_'):
                # Handle UUIDs
                if isinstance(value, UUID):
                    value = str(value)
                # Handle datetime
                elif isinstance(value, datetime):
                    value = value.isoformat()
                log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info) if record.exc_info[2] else None,
            }

        return json.dumps(log_data, default=str)


class StructuredLogger:
    """
    Structured logging for chat system events.

    Usage:
        logger = StructuredLogger()
        logger.log_chat_interaction(
            session_id=123,
            visitor_id="abc",
            user_message="Hello",
            ai_response="Hi there!",
            phase=1,
            intent_score=0,
            processing_time_ms=150
        )
    """

    def __init__(self, name: str = "perennia.chat"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Add JSON handler
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

    def log_chat_interaction(
        self,
        session_id: Any,
        visitor_id: str,
        user_message: str,
        ai_response: str,
        phase: int,
        intent_score: int,
        processing_time_ms: float,
        cached: bool = False,
        model_used: Optional[str] = None,
        tokens_used: Optional[int] = None,
        microsite_id: Optional[int] = None,
    ):
        """Log a chat interaction with full context"""
        self.logger.info(
            "Chat interaction",
            extra={
                "event_type": "chat_interaction",
                "session_id": str(session_id),
                "visitor_id": visitor_id,
                "microsite_id": microsite_id,
                "message_length": len(user_message),
                "response_length": len(ai_response),
                "phase": phase,
                "intent_score": intent_score,
                "processing_time_ms": round(processing_time_ms, 2),
                "cached_response": cached,
                "model_used": model_used,
                "tokens_used": tokens_used,
            }
        )

    def log_cta_event(
        self,
        session_id: Any,
        cta_type: str,
        action: str,  # offered, accepted, declined
        intent_score: int,
        turn_count: int,
        visitor_id: Optional[str] = None,
        microsite_id: Optional[int] = None,
    ):
        """Log CTA events for conversion tracking"""
        self.logger.info(
            f"CTA {action}",
            extra={
                "event_type": "cta_event",
                "session_id": str(session_id),
                "visitor_id": visitor_id,
                "microsite_id": microsite_id,
                "cta_type": cta_type,
                "action": action,
                "intent_score": intent_score,
                "turn_count": turn_count,
            }
        )

    def log_call_event(
        self,
        call_request_id: Any,
        session_id: Any,
        status: str,
        borrower_phone: str,
        lo_phone: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """Log call events for telephony monitoring"""
        # Mask phone numbers for privacy (keep last 4 digits)
        masked_borrower = f"***{borrower_phone[-4:]}" if borrower_phone else None
        masked_lo = f"***{lo_phone[-4:]}" if lo_phone else None

        log_level = logging.ERROR if status == 'failed' else logging.INFO

        self.logger.log(
            log_level,
            f"Call {status}",
            extra={
                "event_type": "call_event",
                "call_request_id": str(call_request_id),
                "session_id": str(session_id),
                "status": status,
                "borrower_phone": masked_borrower,
                "lo_phone": masked_lo,
                "duration_seconds": duration_seconds,
                "error": error,
            }
        )

    def log_phase_transition(
        self,
        session_id: Any,
        from_phase: int,
        to_phase: int,
        intent_score: int,
        turn_count: int,
        trigger: str,  # What caused the transition
    ):
        """Log phase transitions for funnel analysis"""
        self.logger.info(
            f"Phase transition {from_phase} -> {to_phase}",
            extra={
                "event_type": "phase_transition",
                "session_id": str(session_id),
                "from_phase": from_phase,
                "to_phase": to_phase,
                "intent_score": intent_score,
                "turn_count": turn_count,
                "trigger": trigger,
            }
        )

    def log_intent_signal(
        self,
        session_id: Any,
        signal_type: str,
        signal_value: str,
        confidence: float,
        source: str,  # "regex", "enhanced", "ai"
    ):
        """Log detected intent signals"""
        self.logger.info(
            f"Intent signal: {signal_type}",
            extra={
                "event_type": "intent_signal",
                "session_id": str(session_id),
                "signal_type": signal_type,
                "signal_value": signal_value,
                "confidence": round(confidence, 3),
                "source": source,
            }
        )

    def log_error(
        self,
        error_type: str,
        error_message: str,
        session_id: Optional[Any] = None,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log errors with full context"""
        extra = {
            "event_type": "error",
            "error_type": error_type,
            "error_message": error_message,
        }

        if session_id:
            extra["session_id"] = str(session_id)
        if stack_trace:
            extra["stack_trace"] = stack_trace
        if context:
            extra.update(context)

        self.logger.error(error_message, extra=extra)

    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log performance metrics"""
        extra = {
            "event_type": "performance",
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success,
        }

        if metadata:
            extra.update(metadata)

        self.logger.info(f"Performance: {operation}", extra=extra)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests with timing.
    """

    def __init__(self, app, logger: Optional[StructuredLogger] = None):
        super().__init__(app)
        self.structured_logger = logger or StructuredLogger("perennia.http")

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip health checks
        if request.url.path in ['/health', '/api/health', '/metrics']:
            return await call_next(request)

        start_time = time.time()
        request_id = request.headers.get('X-Request-ID', str(time.time()))

        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # Log request
            self.structured_logger.log_performance(
                operation=f"{request.method} {request.url.path}",
                duration_ms=duration_ms,
                success=response.status_code < 400,
                metadata={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "client_ip": request.client.host if request.client else None,
                }
            )

            # Add timing header
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            self.structured_logger.log_error(
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                context={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                }
            )
            raise


def setup_structured_logging(app, log_level: str = "INFO"):
    """
    Configure structured logging for the application.

    Usage in main.py:
        from middleware.structured_logging import setup_structured_logging
        setup_structured_logging(app)
    """
    # Configure root logger
    logging.basicConfig(level=getattr(logging, log_level.upper()))

    # Add request logging middleware
    structured_logger = StructuredLogger()
    app.add_middleware(RequestLoggingMiddleware, logger=structured_logger)

    return structured_logger


# Singleton instance for easy access
_logger_instance: Optional[StructuredLogger] = None


def get_structured_logger() -> StructuredLogger:
    """Get or create the singleton structured logger"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = StructuredLogger()
    return _logger_instance
