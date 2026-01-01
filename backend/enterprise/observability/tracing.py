"""
Distributed Tracing with OpenTelemetry

Provides end-to-end request tracing across services for:
- Performance monitoring
- Error tracking
- Dependency mapping
- Latency analysis

Enterprise Features:
- OpenTelemetry integration
- Jaeger/Zipkin exporters
- W3C Trace Context propagation
- Custom span attributes
- Sampling strategies
"""

import os
import functools
import logging
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Context variable for current trace
_current_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_current_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)


class SpanKind(str, Enum):
    """OpenTelemetry span kinds"""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(str, Enum):
    """Span status codes"""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanContext:
    """Trace context for propagation"""
    trace_id: str
    span_id: str
    trace_flags: int = 1  # Sampled
    trace_state: str = ""

    def to_w3c_traceparent(self) -> str:
        """Convert to W3C traceparent header format"""
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"

    @classmethod
    def from_w3c_traceparent(cls, header: str) -> Optional["SpanContext"]:
        """Parse W3C traceparent header"""
        try:
            parts = header.split("-")
            if len(parts) != 4:
                return None
            return cls(
                trace_id=parts[1],
                span_id=parts[2],
                trace_flags=int(parts[3], 16),
            )
        except Exception:
            return None


class TracingService:
    """
    Distributed Tracing Service using OpenTelemetry.

    Provides automatic instrumentation and manual span creation.
    """

    def __init__(
        self,
        service_name: str = "mortgage-crm",
        environment: Optional[str] = None,
        exporter_type: str = "console",  # console, jaeger, zipkin, otlp
        endpoint: Optional[str] = None,
        sample_rate: float = 1.0,
    ):
        self.service_name = service_name
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.exporter_type = exporter_type
        self.endpoint = endpoint
        self.sample_rate = sample_rate

        self._tracer = None
        self._provider = None
        self._initialized = False

        self._init_tracing()

    def _init_tracing(self):
        """Initialize OpenTelemetry tracing"""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
            from opentelemetry.sdk.resources import Resource

            # Create resource with service info
            resource = Resource.create({
                "service.name": self.service_name,
                "service.environment": self.environment,
                "service.version": os.getenv("VERSION", "1.0.0"),
            })

            # Create sampler
            sampler = TraceIdRatioBased(self.sample_rate)

            # Create provider
            self._provider = TracerProvider(
                resource=resource,
                sampler=sampler,
            )

            # Add exporter
            self._add_exporter()

            # Set global provider
            trace.set_tracer_provider(self._provider)

            # Get tracer
            self._tracer = trace.get_tracer(self.service_name)
            self._initialized = True

            logger.info(f"Tracing initialized with {self.exporter_type} exporter")

        except ImportError as e:
            logger.warning(f"OpenTelemetry not installed, tracing disabled: {e}")
            self._initialized = False

    def _add_exporter(self):
        """Add the configured exporter"""
        try:
            if self.exporter_type == "console":
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
                processor = SimpleSpanProcessor(ConsoleSpanExporter())
                self._provider.add_span_processor(processor)

            elif self.exporter_type == "jaeger":
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter = JaegerExporter(
                    agent_host_name=self.endpoint or "localhost",
                    agent_port=6831,
                )
                processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)

            elif self.exporter_type == "zipkin":
                from opentelemetry.exporter.zipkin.json import ZipkinExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter = ZipkinExporter(
                    endpoint=self.endpoint or "http://localhost:9411/api/v2/spans",
                )
                processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)

            elif self.exporter_type == "otlp":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter = OTLPSpanExporter(
                    endpoint=self.endpoint or "http://localhost:4317",
                )
                processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)

        except ImportError as e:
            logger.warning(f"Exporter {self.exporter_type} not available: {e}")

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        parent_context: Optional[SpanContext] = None,
    ):
        """
        Start a new span as a context manager.

        Usage:
            with tracing.start_span("process_loan", attributes={"loan_id": "123"}):
                # ... processing
        """
        if not self._initialized or not self._tracer:
            yield None
            return

        from opentelemetry import trace
        from opentelemetry.trace import SpanKind as OTelSpanKind

        # Map span kind
        kind_map = {
            SpanKind.INTERNAL: OTelSpanKind.INTERNAL,
            SpanKind.SERVER: OTelSpanKind.SERVER,
            SpanKind.CLIENT: OTelSpanKind.CLIENT,
            SpanKind.PRODUCER: OTelSpanKind.PRODUCER,
            SpanKind.CONSUMER: OTelSpanKind.CONSUMER,
        }

        # Start span
        with self._tracer.start_as_current_span(
            name,
            kind=kind_map.get(kind, OTelSpanKind.INTERNAL),
            attributes=attributes,
        ) as span:
            # Store trace context
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, '032x')
            span_id = format(ctx.span_id, '016x')

            _current_trace_id.set(trace_id)
            _current_span_id.set(span_id)

            try:
                yield span
            except Exception as e:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    def add_span_attribute(self, key: str, value: Any):
        """Add an attribute to the current span"""
        if not self._initialized:
            return

        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            span.set_attribute(key, value)

    def add_span_event(self, name: str, attributes: Optional[Dict] = None):
        """Add an event to the current span"""
        if not self._initialized:
            return

        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            span.add_event(name, attributes)

    def record_exception(self, exception: Exception, attributes: Optional[Dict] = None):
        """Record an exception on the current span"""
        if not self._initialized:
            return

        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            span.record_exception(exception, attributes)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))

    def get_current_context(self) -> Optional[SpanContext]:
        """Get the current trace context"""
        trace_id = _current_trace_id.get()
        span_id = _current_span_id.get()

        if trace_id and span_id:
            return SpanContext(trace_id=trace_id, span_id=span_id)
        return None

    def inject_context(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Inject trace context into headers for propagation"""
        ctx = self.get_current_context()
        if ctx:
            headers["traceparent"] = ctx.to_w3c_traceparent()
        return headers

    def extract_context(self, headers: Dict[str, str]) -> Optional[SpanContext]:
        """Extract trace context from incoming headers"""
        traceparent = headers.get("traceparent")
        if traceparent:
            return SpanContext.from_w3c_traceparent(traceparent)
        return None

    def shutdown(self):
        """Shutdown the tracer and flush pending spans"""
        if self._provider:
            self._provider.shutdown()
            logger.info("Tracing shutdown complete")


# Global tracing instance
_tracing_service: Optional[TracingService] = None


def init_tracing(**kwargs) -> TracingService:
    """Initialize the global tracing service"""
    global _tracing_service
    _tracing_service = TracingService(**kwargs)
    return _tracing_service


def get_tracing() -> Optional[TracingService]:
    """Get the global tracing service"""
    return _tracing_service


def get_current_trace_id() -> Optional[str]:
    """Get the current trace ID"""
    return _current_trace_id.get()


def get_current_span_id() -> Optional[str]:
    """Get the current span ID"""
    return _current_span_id.get()


# Decorator for tracing functions
def trace_span(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to trace a function.

    Usage:
        @trace_span("process_loan")
        async def process_loan(loan_id: str):
            ...

        @trace_span(attributes={"component": "ai"})
        def analyze_credit(data: dict):
            ...
    """
    def decorator(func: Callable):
        span_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracing = get_tracing()
            if not tracing:
                return await func(*args, **kwargs)

            with tracing.start_span(span_name, kind=kind, attributes=attributes):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracing = get_tracing()
            if not tracing:
                return func(*args, **kwargs)

            with tracing.start_span(span_name, kind=kind, attributes=attributes):
                return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# FastAPI middleware for automatic request tracing
class TracingMiddleware:
    """
    FastAPI middleware for automatic request tracing.

    Usage:
        from fastapi import FastAPI
        from enterprise.observability.tracing import TracingMiddleware

        app = FastAPI()
        app.add_middleware(TracingMiddleware)
    """

    def __init__(self, app, tracing_service: Optional[TracingService] = None):
        self.app = app
        self.tracing = tracing_service or get_tracing()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.tracing:
            await self.app(scope, receive, send)
            return

        # Extract incoming context
        headers = dict(scope.get("headers", []))
        headers = {k.decode(): v.decode() for k, v in headers.items() if isinstance(k, bytes)}
        parent_context = self.tracing.extract_context(headers)

        # Determine span name from path
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        span_name = f"{method} {path}"

        # Start request span
        with self.tracing.start_span(
            span_name,
            kind=SpanKind.SERVER,
            attributes={
                "http.method": method,
                "http.url": path,
                "http.scheme": scope.get("scheme", "http"),
                "http.host": headers.get("host", ""),
                "http.user_agent": headers.get("user-agent", ""),
            },
        ) as span:
            # Track response status
            status_code = 500

            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                    if span:
                        span.set_attribute("http.status_code", status_code)
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                if span:
                    span.record_exception(e)
                raise
