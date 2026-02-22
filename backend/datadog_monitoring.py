"""
DataDog Monitoring Integration
==============================
Comprehensive monitoring for the Mortgage CRM:
- APM (Application Performance Monitoring) via ddtrace
- Custom business metrics
- Log forwarding integration
- Dashboard configuration export

Environment Variables:
    DD_API_KEY: DataDog API key (required for metrics)
    DD_APP_KEY: DataDog App key (for dashboard management)
    DD_SERVICE: Service name (default: mortgage-crm)
    DD_ENV: Environment (default: from ENVIRONMENT)
    DD_TRACE_ENABLED: Enable APM tracing (default: true)
    DD_LOGS_INJECTION: Enable log correlation (default: true)
"""

import os
import time
import logging
import functools
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

DD_API_KEY = os.getenv("DD_API_KEY", "")
DD_APP_KEY = os.getenv("DD_APP_KEY", "")
DD_SERVICE = os.getenv("DD_SERVICE", "mortgage-crm")
DD_ENV = os.getenv("DD_ENV") or os.getenv("ENVIRONMENT", "development")
DD_TRACE_ENABLED = os.getenv("DD_TRACE_ENABLED", "true").lower() == "true"
DD_LOGS_INJECTION = os.getenv("DD_LOGS_INJECTION", "true").lower() == "true"

# Module state
_tracer = None
_statsd = None
_initialized = False


# ============================================================================
# APM TRACING (ddtrace)
# ============================================================================

def init_tracer():
    """
    Initialize DataDog APM tracer.

    This should be called as early as possible in the application lifecycle,
    ideally before importing other modules.
    """
    global _tracer, _initialized

    if not DD_TRACE_ENABLED:
        logger.info("DataDog tracing disabled (DD_TRACE_ENABLED=false)")
        return None

    try:
        from ddtrace import tracer, patch_all, config

        # Configure service name and environment
        config.service = DD_SERVICE
        config.env = DD_ENV

        # Enable log injection for correlation
        if DD_LOGS_INJECTION:
            config.logs_injection = True

        # Patch all supported libraries automatically
        # This includes: FastAPI, SQLAlchemy, Redis, httpx, aiohttp, etc.
        patch_all(
            fastapi=True,
            sqlalchemy=True,
            redis=True,
            httpx=True,
            aiohttp=True,
            logging=DD_LOGS_INJECTION,
        )

        _tracer = tracer
        _initialized = True

        logger.info(f"✅ DataDog APM initialized: service={DD_SERVICE}, env={DD_ENV}")
        return tracer

    except ImportError:
        logger.warning("ddtrace not installed - run: pip install ddtrace")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize DataDog APM: {e}")
        return None


def get_tracer():
    """Get the DataDog tracer instance."""
    global _tracer
    if _tracer is None:
        init_tracer()
    return _tracer


# ============================================================================
# CUSTOM METRICS (DogStatsD)
# ============================================================================

def init_statsd():
    """
    Initialize DogStatsD client for custom metrics.

    Requires the DataDog agent running locally or DD_AGENT_HOST configured.
    """
    global _statsd

    try:
        from datadog import initialize, statsd

        options = {
            'statsd_host': os.getenv('DD_AGENT_HOST', '127.0.0.1'),
            'statsd_port': int(os.getenv('DD_DOGSTATSD_PORT', 8125)),
            'statsd_constant_tags': [
                f'service:{DD_SERVICE}',
                f'env:{DD_ENV}',
            ]
        }

        # Initialize with API key if available (for direct submission)
        if DD_API_KEY:
            options['api_key'] = DD_API_KEY

        initialize(**options)
        _statsd = statsd

        logger.info("✅ DataDog StatsD client initialized")
        return statsd

    except ImportError:
        logger.warning("datadog not installed - run: pip install datadog")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize DogStatsD: {e}")
        return None


def get_statsd():
    """Get the DogStatsD client instance."""
    global _statsd
    if _statsd is None:
        init_statsd()
    return _statsd


# ============================================================================
# METRIC HELPERS
# ============================================================================

class MetricsCollector:
    """
    Helper class for collecting business metrics.

    Usage:
        metrics = MetricsCollector()
        metrics.increment('leads.created', tags=['source:website'])
        metrics.gauge('pipeline.value', 1500000, tags=['lo:john'])
        metrics.histogram('api.response_time', 0.234, tags=['endpoint:leads'])
    """

    def __init__(self):
        self.statsd = get_statsd()
        self.prefix = "mortgage_crm"

    def _metric_name(self, name: str) -> str:
        """Build full metric name with prefix."""
        return f"{self.prefix}.{name}"

    def increment(self, name: str, value: int = 1, tags: List[str] = None):
        """Increment a counter metric."""
        if self.statsd:
            try:
                self.statsd.increment(self._metric_name(name), value, tags=tags)
            except Exception as e:
                logger.debug(f"Failed to send metric {name}: {e}")

    def decrement(self, name: str, value: int = 1, tags: List[str] = None):
        """Decrement a counter metric."""
        if self.statsd:
            try:
                self.statsd.decrement(self._metric_name(name), value, tags=tags)
            except Exception as e:
                logger.debug(f"Failed to send metric {name}: {e}")

    def gauge(self, name: str, value: float, tags: List[str] = None):
        """Set a gauge metric."""
        if self.statsd:
            try:
                self.statsd.gauge(self._metric_name(name), value, tags=tags)
            except Exception as e:
                logger.debug(f"Failed to send metric {name}: {e}")

    def histogram(self, name: str, value: float, tags: List[str] = None):
        """Record a histogram/distribution metric."""
        if self.statsd:
            try:
                self.statsd.histogram(self._metric_name(name), value, tags=tags)
            except Exception as e:
                logger.debug(f"Failed to send metric {name}: {e}")

    def timing(self, name: str, value_ms: float, tags: List[str] = None):
        """Record a timing metric in milliseconds."""
        if self.statsd:
            try:
                self.statsd.timing(self._metric_name(name), value_ms, tags=tags)
            except Exception as e:
                logger.debug(f"Failed to send metric {name}: {e}")

    def event(self, title: str, text: str, alert_type: str = "info", tags: List[str] = None):
        """Send an event to DataDog."""
        if self.statsd:
            try:
                self.statsd.event(
                    title=title,
                    text=text,
                    alert_type=alert_type,
                    tags=tags or []
                )
            except Exception as e:
                logger.debug(f"Failed to send event {title}: {e}")

    @contextmanager
    def timed(self, name: str, tags: List[str] = None):
        """Context manager for timing code blocks."""
        start = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            self.timing(name, duration_ms, tags=tags)


# Global metrics collector instance
metrics = MetricsCollector()


# ============================================================================
# BUSINESS METRICS
# ============================================================================

class BusinessMetrics:
    """
    Domain-specific metrics for the Mortgage CRM.

    These metrics provide visibility into:
    - Lead pipeline health
    - Loan processing efficiency
    - User engagement
    - AI performance
    """

    def __init__(self, collector: MetricsCollector = None):
        self.metrics = collector or metrics

    # Lead Metrics
    def lead_created(self, source: str = None, lo_id: int = None):
        """Track new lead creation."""
        tags = []
        if source:
            tags.append(f"source:{source}")
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("leads.created", tags=tags)

    def lead_converted(self, source: str = None, lo_id: int = None, days_to_convert: int = None):
        """Track lead conversion to loan."""
        tags = []
        if source:
            tags.append(f"source:{source}")
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("leads.converted", tags=tags)

        if days_to_convert is not None:
            self.metrics.histogram("leads.days_to_convert", days_to_convert, tags=tags)

    def lead_stage_changed(self, from_stage: str, to_stage: str, lo_id: int = None):
        """Track lead stage transitions."""
        tags = [f"from:{from_stage}", f"to:{to_stage}"]
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("leads.stage_change", tags=tags)

    # Loan Metrics
    def loan_created(self, loan_type: str = None, lo_id: int = None, amount: float = None):
        """Track new loan creation."""
        tags = []
        if loan_type:
            tags.append(f"type:{loan_type}")
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("loans.created", tags=tags)

        if amount:
            self.metrics.histogram("loans.amount", amount, tags=tags)

    def loan_funded(self, loan_type: str = None, lo_id: int = None, amount: float = None, cycle_days: int = None):
        """Track loan funding."""
        tags = []
        if loan_type:
            tags.append(f"type:{loan_type}")
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("loans.funded", tags=tags)

        if amount:
            self.metrics.histogram("loans.funded_amount", amount, tags=tags)
        if cycle_days:
            self.metrics.histogram("loans.cycle_days", cycle_days, tags=tags)

    def loan_stage_changed(self, from_stage: str, to_stage: str, lo_id: int = None):
        """Track loan stage transitions."""
        tags = [f"from:{from_stage}", f"to:{to_stage}"]
        if lo_id:
            tags.append(f"lo_id:{lo_id}")
        self.metrics.increment("loans.stage_change", tags=tags)

    # Pipeline Metrics (gauges - current state)
    def pipeline_snapshot(self, total_loans: int, total_volume: float, by_stage: Dict[str, int] = None):
        """Record current pipeline state."""
        self.metrics.gauge("pipeline.total_loans", total_loans)
        self.metrics.gauge("pipeline.total_volume", total_volume)

        if by_stage:
            for stage, count in by_stage.items():
                self.metrics.gauge("pipeline.by_stage", count, tags=[f"stage:{stage}"])

    # AI Metrics
    def ai_request(self, model: str, request_type: str, duration_ms: float, tokens: int = None, success: bool = True):
        """Track AI model usage."""
        tags = [f"model:{model}", f"type:{request_type}", f"success:{success}"]
        self.metrics.increment("ai.requests", tags=tags)
        self.metrics.histogram("ai.duration_ms", duration_ms, tags=tags)

        if tokens:
            self.metrics.histogram("ai.tokens", tokens, tags=tags)

    def ai_receptionist_call(self, duration_seconds: float, outcome: str, appointment_scheduled: bool = False):
        """Track AI receptionist call metrics."""
        tags = [f"outcome:{outcome}", f"appointment:{appointment_scheduled}"]
        self.metrics.increment("ai_receptionist.calls", tags=tags)
        self.metrics.histogram("ai_receptionist.duration", duration_seconds, tags=tags)

    # User Activity
    def user_login(self, user_id: int, role: str = None):
        """Track user logins."""
        tags = []
        if role:
            tags.append(f"role:{role}")
        self.metrics.increment("users.login", tags=tags)

    def api_request(self, endpoint: str, method: str, status_code: int, duration_ms: float):
        """Track API request metrics."""
        tags = [f"endpoint:{endpoint}", f"method:{method}", f"status:{status_code}"]
        self.metrics.increment("api.requests", tags=tags)
        self.metrics.histogram("api.duration_ms", duration_ms, tags=tags)


# Global business metrics instance
business_metrics = BusinessMetrics()


# ============================================================================
# DECORATORS
# ============================================================================

def trace_function(name: str = None, service: str = None, resource: str = None):
    """
    Decorator to trace function execution with DataDog APM.

    Usage:
        @trace_function("my_operation")
        def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer:
                span_name = name or func.__name__
                with tracer.trace(span_name, service=service, resource=resource):
                    return await func(*args, **kwargs)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer:
                span_name = name or func.__name__
                with tracer.trace(span_name, service=service, resource=resource):
                    return func(*args, **kwargs)
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_metric(metric_name: str, tags: List[str] = None, track_timing: bool = True):
    """
    Decorator to automatically track function metrics.

    Usage:
        @track_metric("leads.process", tags=["type:api"])
        def process_lead():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            success = True
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Error in tracked async function {func.__name__}: {e}")
                success = False
                raise
            finally:
                all_tags = list(tags or [])
                all_tags.append(f"success:{success}")

                metrics.increment(metric_name, tags=all_tags)

                if track_timing:
                    duration_ms = (time.time() - start) * 1000
                    metrics.timing(f"{metric_name}.duration", duration_ms, tags=all_tags)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            success = True
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Error in tracked sync function {func.__name__}: {e}")
                success = False
                raise
            finally:
                all_tags = list(tags or [])
                all_tags.append(f"success:{success}")

                metrics.increment(metric_name, tags=all_tags)

                if track_timing:
                    duration_ms = (time.time() - start) * 1000
                    metrics.timing(f"{metric_name}.duration", duration_ms, tags=all_tags)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

class DataDogMiddleware:
    """
    FastAPI middleware for DataDog metrics collection.

    This middleware:
    - Records request count and duration metrics
    - Adds trace context to logs
    - Tracks error rates
    """

    def __init__(self, app, exclude_paths: List[str] = None):
        self.app = app
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start_time = time.time()
        status_code = 500  # Default to error

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.time() - start_time) * 1000

            # Normalize path for metric tags (replace IDs with placeholder)
            import re
            normalized_path = re.sub(r'/\d+', '/{id}', path)
            normalized_path = re.sub(r'/[a-f0-9-]{36}', '/{uuid}', normalized_path)

            tags = [
                f"path:{normalized_path}",
                f"method:{method}",
                f"status:{status_code}",
                f"status_class:{status_code // 100}xx"
            ]

            metrics.increment("http.requests", tags=tags)
            metrics.histogram("http.duration_ms", duration_ms, tags=tags)

            if status_code >= 500:
                metrics.increment("http.errors.5xx", tags=tags)
            elif status_code >= 400:
                metrics.increment("http.errors.4xx", tags=tags)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_datadog_monitoring(app=None):
    """
    Initialize DataDog monitoring for the application.

    Call this early in application startup:
        from datadog_monitoring import setup_datadog_monitoring
        setup_datadog_monitoring(app)

    Returns dict with initialization status.
    """
    result = {
        "apm_enabled": False,
        "metrics_enabled": False,
        "service": DD_SERVICE,
        "environment": DD_ENV
    }

    # Initialize APM tracer
    tracer = init_tracer()
    result["apm_enabled"] = tracer is not None

    # Initialize StatsD client
    statsd = init_statsd()
    result["metrics_enabled"] = statsd is not None

    # Add middleware to FastAPI app if provided
    if app is not None:
        try:
            from starlette.middleware import Middleware
            app.add_middleware(DataDogMiddleware)
            result["middleware_added"] = True
            logger.info("✅ DataDog middleware added to FastAPI app")
        except Exception as e:
            logger.warning(f"Failed to add DataDog middleware: {e}")
            result["middleware_added"] = False

    # Send initialization event
    if result["metrics_enabled"]:
        metrics.event(
            title="Mortgage CRM Started",
            text=f"Service {DD_SERVICE} started in {DD_ENV} environment",
            alert_type="info",
            tags=[f"service:{DD_SERVICE}", f"env:{DD_ENV}"]
        )

    logger.info(f"✅ DataDog monitoring setup complete: {result}")
    return result


# ============================================================================
# DASHBOARD CONFIGURATION
# ============================================================================

def get_dashboard_config() -> Dict[str, Any]:
    """
    Returns DataDog dashboard configuration as JSON.

    This can be used with DataDog's Dashboard API to create/update dashboards.
    """
    return {
        "title": f"Mortgage CRM - {DD_ENV.title()}",
        "description": "Real-time monitoring for the Agentic AI Mortgage CRM",
        "widgets": [
            # Request Rate
            {
                "id": 1,
                "definition": {
                    "title": "Request Rate",
                    "type": "timeseries",
                    "requests": [
                        {
                            "q": f"sum:mortgage_crm.http.requests{{service:{DD_SERVICE}}}.as_rate()",
                            "display_type": "bars"
                        }
                    ]
                }
            },
            # Response Time P50/P95/P99
            {
                "id": 2,
                "definition": {
                    "title": "Response Time Percentiles",
                    "type": "timeseries",
                    "requests": [
                        {"q": f"p50:mortgage_crm.http.duration_ms{{service:{DD_SERVICE}}}", "display_type": "line"},
                        {"q": f"p95:mortgage_crm.http.duration_ms{{service:{DD_SERVICE}}}", "display_type": "line"},
                        {"q": f"p99:mortgage_crm.http.duration_ms{{service:{DD_SERVICE}}}", "display_type": "line"}
                    ]
                }
            },
            # Error Rate
            {
                "id": 3,
                "definition": {
                    "title": "Error Rate",
                    "type": "timeseries",
                    "requests": [
                        {
                            "q": f"sum:mortgage_crm.http.errors.5xx{{service:{DD_SERVICE}}}.as_rate() / sum:mortgage_crm.http.requests{{service:{DD_SERVICE}}}.as_rate() * 100",
                            "display_type": "line"
                        }
                    ]
                }
            },
            # Leads Created
            {
                "id": 4,
                "definition": {
                    "title": "Leads Created (24h)",
                    "type": "query_value",
                    "requests": [
                        {"q": f"sum:mortgage_crm.leads.created{{service:{DD_SERVICE}}}.rollup(sum, 86400)"}
                    ]
                }
            },
            # Loans Funded
            {
                "id": 5,
                "definition": {
                    "title": "Loans Funded (24h)",
                    "type": "query_value",
                    "requests": [
                        {"q": f"sum:mortgage_crm.loans.funded{{service:{DD_SERVICE}}}.rollup(sum, 86400)"}
                    ]
                }
            },
            # Pipeline Value
            {
                "id": 6,
                "definition": {
                    "title": "Current Pipeline Value",
                    "type": "query_value",
                    "requests": [
                        {"q": f"avg:mortgage_crm.pipeline.total_volume{{service:{DD_SERVICE}}}"}
                    ],
                    "custom_unit": "$"
                }
            },
            # AI Receptionist Calls
            {
                "id": 7,
                "definition": {
                    "title": "AI Receptionist Calls",
                    "type": "timeseries",
                    "requests": [
                        {"q": f"sum:mortgage_crm.ai_receptionist.calls{{service:{DD_SERVICE}}}.as_count()", "display_type": "bars"}
                    ]
                }
            },
            # AI Request Duration
            {
                "id": 8,
                "definition": {
                    "title": "AI Request Duration",
                    "type": "timeseries",
                    "requests": [
                        {"q": f"avg:mortgage_crm.ai.duration_ms{{service:{DD_SERVICE}}} by {{model}}", "display_type": "line"}
                    ]
                }
            }
        ],
        "layout_type": "ordered",
        "notify_list": [],
        "template_variables": [
            {"name": "env", "default": DD_ENV, "prefix": "env"}
        ]
    }


def export_dashboard_json(filename: str = "datadog_dashboard.json"):
    """Export dashboard configuration to JSON file."""
    import json
    config = get_dashboard_config()
    with open(filename, 'w') as f:
        json.dump(config, f, indent=2)
    logger.info(f"Dashboard configuration exported to {filename}")
    return filename
