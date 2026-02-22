"""
Prometheus Metrics for Call Intelligence Service

Provides observability into extraction performance, quality, and errors.

Usage:
    from services.call_intelligence.metrics import (
        track_extraction,
        track_error,
        get_metrics_handler,
    )

    # Track successful extraction
    track_extraction(
        method="unified",
        duration_ms=1234,
        field_count=25,
        high_confidence_count=20,
    )

    # Track error
    track_error("llm_timeout", method="unified")

    # Expose metrics endpoint (FastAPI)
    app.add_route("/metrics", get_metrics_handler())

Metrics Exposed:
    - call_intelligence_extractions_total: Counter of extractions by method
    - call_intelligence_extraction_duration_ms: Histogram of processing time
    - call_intelligence_fields_extracted: Histogram of fields per extraction
    - call_intelligence_confidence_distribution: Histogram of confidence scores
    - call_intelligence_errors_total: Counter of errors by type
    - call_intelligence_pii_redactions_total: Counter of PII redactions by type
"""

import time
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import wraps

logger = logging.getLogger(__name__)


# =============================================================================
# Metrics Storage (In-Memory)
# =============================================================================
# For production, replace with prometheus_client library
# This implementation provides the same interface without external deps

@dataclass
class Counter:
    """Simple counter metric."""
    name: str
    help: str
    labels: list = field(default_factory=list)
    _values: Dict[tuple, float] = field(default_factory=dict)

    def inc(self, value: float = 1, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] = self._values.get(key, 0) + value

    def get(self, **label_values) -> float:
        key = tuple(label_values.get(l, "") for l in self.labels)
        return self._values.get(key, 0)

    def collect(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "help": self.help,
            "type": "counter",
            "values": [
                {"labels": dict(zip(self.labels, k)), "value": v}
                for k, v in self._values.items()
            ],
        }


@dataclass
class Histogram:
    """Simple histogram metric with buckets."""
    name: str
    help: str
    labels: list = field(default_factory=list)
    buckets: list = field(default_factory=lambda: [10, 50, 100, 250, 500, 1000, 2500, 5000, 10000])
    _values: Dict[tuple, list] = field(default_factory=dict)

    def observe(self, value: float, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        if key not in self._values:
            self._values[key] = []
        self._values[key].append(value)

    def get_stats(self, **label_values) -> Dict[str, float]:
        key = tuple(label_values.get(l, "") for l in self.labels)
        values = self._values.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def collect(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "help": self.help,
            "type": "histogram",
            "buckets": self.buckets,
            "values": [],
        }
        for key, values in self._values.items():
            bucket_counts = {b: sum(1 for v in values if v <= b) for b in self.buckets}
            bucket_counts["+Inf"] = len(values)
            result["values"].append({
                "labels": dict(zip(self.labels, key)),
                "bucket_counts": bucket_counts,
                "count": len(values),
                "sum": sum(values),
            })
        return result


@dataclass
class Gauge:
    """Simple gauge metric."""
    name: str
    help: str
    labels: list = field(default_factory=list)
    _values: Dict[tuple, float] = field(default_factory=dict)

    def set(self, value: float, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] = value

    def inc(self, value: float = 1, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] = self._values.get(key, 0) + value

    def dec(self, value: float = 1, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] = self._values.get(key, 0) - value

    def get(self, **label_values) -> float:
        key = tuple(label_values.get(l, "") for l in self.labels)
        return self._values.get(key, 0)

    def collect(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "help": self.help,
            "type": "gauge",
            "values": [
                {"labels": dict(zip(self.labels, k)), "value": v}
                for k, v in self._values.items()
            ],
        }


# =============================================================================
# Call Intelligence Metrics
# =============================================================================

# Extraction counters
EXTRACTIONS_TOTAL = Counter(
    name="call_intelligence_extractions_total",
    help="Total number of transcript extractions",
    labels=["method", "status"],  # method: unified/parallel_agents, status: success/failure
)

# Processing time histogram
EXTRACTION_DURATION = Histogram(
    name="call_intelligence_extraction_duration_ms",
    help="Extraction processing time in milliseconds",
    labels=["method"],
    buckets=[100, 250, 500, 1000, 2000, 5000, 10000, 30000],
)

# Fields extracted histogram
FIELDS_EXTRACTED = Histogram(
    name="call_intelligence_fields_extracted",
    help="Number of fields extracted per transcript",
    labels=["method"],
    buckets=[5, 10, 15, 20, 25, 30, 40, 50],
)

# Confidence score histogram
CONFIDENCE_SCORES = Histogram(
    name="call_intelligence_confidence_score",
    help="Distribution of extraction confidence scores",
    labels=["method", "domain"],  # domain: identity/property/employment/etc
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

# High/low confidence counters
HIGH_CONFIDENCE_COUNT = Counter(
    name="call_intelligence_high_confidence_total",
    help="Count of extractions with confidence >= 90",
    labels=["method"],
)

LOW_CONFIDENCE_COUNT = Counter(
    name="call_intelligence_low_confidence_total",
    help="Count of extractions with confidence < 70",
    labels=["method"],
)

# Error counter
ERRORS_TOTAL = Counter(
    name="call_intelligence_errors_total",
    help="Total number of extraction errors",
    labels=["method", "error_type"],  # error_type: llm_timeout/parse_error/rate_limit/etc
)

# PII redaction counter
PII_REDACTIONS = Counter(
    name="call_intelligence_pii_redactions_total",
    help="Count of PII items redacted before LLM calls",
    labels=["pii_type"],  # pii_type: ssn/dob/phone/email/etc
)

# Active extractions gauge (for concurrent processing)
ACTIVE_EXTRACTIONS = Gauge(
    name="call_intelligence_active_extractions",
    help="Number of extractions currently in progress",
    labels=["method"],
)

# LLM API metrics
LLM_REQUESTS_TOTAL = Counter(
    name="call_intelligence_llm_requests_total",
    help="Total LLM API requests",
    labels=["provider", "status"],  # provider: anthropic/openai
)

LLM_REQUEST_DURATION = Histogram(
    name="call_intelligence_llm_request_duration_ms",
    help="LLM API request duration in milliseconds",
    labels=["provider"],
    buckets=[500, 1000, 2000, 5000, 10000, 20000, 30000],
)

LLM_TOKENS_USED = Counter(
    name="call_intelligence_llm_tokens_total",
    help="Total LLM tokens used (approximate)",
    labels=["provider", "direction"],  # direction: input/output
)


# =============================================================================
# Tracking Functions
# =============================================================================

def track_extraction(
    method: str,
    duration_ms: int,
    field_count: int = 0,
    high_confidence_count: int = 0,
    low_confidence_count: int = 0,
    success: bool = True,
):
    """
    Track a completed extraction.

    Args:
        method: Extraction method (unified, parallel_agents, streaming)
        duration_ms: Processing time in milliseconds
        field_count: Number of fields extracted
        high_confidence_count: Fields with confidence >= 90
        low_confidence_count: Fields with confidence < 70
        success: Whether extraction succeeded
    """
    status = "success" if success else "failure"
    EXTRACTIONS_TOTAL.inc(method=method, status=status)
    EXTRACTION_DURATION.observe(duration_ms, method=method)

    if field_count > 0:
        FIELDS_EXTRACTED.observe(field_count, method=method)

    if high_confidence_count > 0:
        HIGH_CONFIDENCE_COUNT.inc(high_confidence_count, method=method)

    if low_confidence_count > 0:
        LOW_CONFIDENCE_COUNT.inc(low_confidence_count, method=method)

    logger.debug(
        f"Tracked extraction: method={method}, duration={duration_ms}ms, "
        f"fields={field_count}, high_conf={high_confidence_count}"
    )


def track_confidence(method: str, domain: str, confidence: float):
    """Track individual confidence score."""
    CONFIDENCE_SCORES.observe(confidence, method=method, domain=domain)


def track_error(error_type: str, method: str = "unknown"):
    """
    Track an extraction error.

    Args:
        error_type: Type of error (llm_timeout, parse_error, rate_limit, validation)
        method: Extraction method when error occurred
    """
    ERRORS_TOTAL.inc(method=method, error_type=error_type)
    logger.debug(f"Tracked error: type={error_type}, method={method}")


def track_pii_redaction(pii_type: str, count: int = 1):
    """
    Track PII redaction.

    Args:
        pii_type: Type of PII redacted (ssn, dob, phone, email, etc)
        count: Number of items redacted
    """
    PII_REDACTIONS.inc(count, pii_type=pii_type)


def track_pii_stats(stats: Dict[str, int]):
    """Track PII redaction stats from redact_transcript_for_llm()."""
    for pii_type, count in stats.items():
        if pii_type != "total" and count > 0:
            track_pii_redaction(pii_type, count)


def track_llm_request(
    provider: str,
    duration_ms: int,
    success: bool = True,
    input_tokens: int = 0,
    output_tokens: int = 0,
):
    """
    Track an LLM API request.

    Args:
        provider: LLM provider (anthropic, openai)
        duration_ms: Request duration in milliseconds
        success: Whether request succeeded
        input_tokens: Approximate input tokens
        output_tokens: Approximate output tokens
    """
    status = "success" if success else "failure"
    LLM_REQUESTS_TOTAL.inc(provider=provider, status=status)
    LLM_REQUEST_DURATION.observe(duration_ms, provider=provider)

    if input_tokens > 0:
        LLM_TOKENS_USED.inc(input_tokens, provider=provider, direction="input")
    if output_tokens > 0:
        LLM_TOKENS_USED.inc(output_tokens, provider=provider, direction="output")


@contextmanager
def track_extraction_context(method: str):
    """
    Context manager to track extraction timing.

    Usage:
        with track_extraction_context("unified") as tracker:
            result = await process_transcript(...)
            tracker.set_fields(result.total_extractions)
    """
    class Tracker:
        def __init__(self):
            self.field_count = 0
            self.high_confidence = 0
            self.low_confidence = 0
            self.success = True

        def set_fields(self, count: int, high: int = 0, low: int = 0):
            self.field_count = count
            self.high_confidence = high
            self.low_confidence = low

        def set_failure(self):
            self.success = False

    tracker = Tracker()
    ACTIVE_EXTRACTIONS.inc(method=method)
    start_time = time.time()

    try:
        yield tracker
    except Exception as e:
        logger.error(f"Error in track_extraction_metrics: {e}")
        tracker.set_failure()
        raise
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        ACTIVE_EXTRACTIONS.dec(method=method)
        track_extraction(
            method=method,
            duration_ms=duration_ms,
            field_count=tracker.field_count,
            high_confidence_count=tracker.high_confidence,
            low_confidence_count=tracker.low_confidence,
            success=tracker.success,
        )


# =============================================================================
# Metrics Export
# =============================================================================

ALL_METRICS = [
    EXTRACTIONS_TOTAL,
    EXTRACTION_DURATION,
    FIELDS_EXTRACTED,
    CONFIDENCE_SCORES,
    HIGH_CONFIDENCE_COUNT,
    LOW_CONFIDENCE_COUNT,
    ERRORS_TOTAL,
    PII_REDACTIONS,
    ACTIVE_EXTRACTIONS,
    LLM_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION,
    LLM_TOKENS_USED,
]


def collect_metrics() -> Dict[str, Any]:
    """Collect all metrics as a dictionary."""
    return {
        "metrics": [m.collect() for m in ALL_METRICS],
        "timestamp": time.time(),
    }


def format_prometheus() -> str:
    """Format metrics in Prometheus exposition format."""
    lines = []

    for metric in ALL_METRICS:
        data = metric.collect()
        lines.append(f"# HELP {data['name']} {data['help']}")
        lines.append(f"# TYPE {data['name']} {data['type']}")

        for value in data.get("values", []):
            labels = value.get("labels", {})
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            label_str = f"{{{label_str}}}" if label_str else ""

            if data["type"] == "histogram":
                # Output bucket counts
                for bucket, count in value.get("bucket_counts", {}).items():
                    bucket_label = f'le="{bucket}"'
                    full_labels = f"{{{label_str},{bucket_label}}}" if label_str else f"{{{bucket_label}}}"
                    lines.append(f"{data['name']}_bucket{full_labels} {count}")
                lines.append(f"{data['name']}_count{label_str} {value.get('count', 0)}")
                lines.append(f"{data['name']}_sum{label_str} {value.get('sum', 0)}")
            else:
                lines.append(f"{data['name']}{label_str} {value.get('value', 0)}")

    return "\n".join(lines)


def get_metrics_handler():
    """
    Get a handler function for /metrics endpoint.

    Works with FastAPI, Flask, or plain ASGI.

    Usage (FastAPI):
        from fastapi import Response
        @app.get("/metrics")
        def metrics():
            return Response(get_metrics_handler()(), media_type="text/plain")
    """
    def handler():
        return format_prometheus()
    return handler


def get_metrics_summary() -> Dict[str, Any]:
    """Get a human-readable summary of key metrics."""
    unified_success = EXTRACTIONS_TOTAL.get(method="unified", status="success")
    unified_failure = EXTRACTIONS_TOTAL.get(method="unified", status="failure")
    agents_success = EXTRACTIONS_TOTAL.get(method="parallel_agents", status="success")
    agents_failure = EXTRACTIONS_TOTAL.get(method="parallel_agents", status="failure")

    unified_stats = EXTRACTION_DURATION.get_stats(method="unified")
    agents_stats = EXTRACTION_DURATION.get_stats(method="parallel_agents")

    return {
        "extractions": {
            "unified": {
                "success": unified_success,
                "failure": unified_failure,
                "total": unified_success + unified_failure,
            },
            "parallel_agents": {
                "success": agents_success,
                "failure": agents_failure,
                "total": agents_success + agents_failure,
            },
        },
        "duration_ms": {
            "unified": unified_stats,
            "parallel_agents": agents_stats,
        },
        "errors": {
            "total": sum(ERRORS_TOTAL._values.values()),
        },
        "pii_redacted": {
            "total": sum(PII_REDACTIONS._values.values()),
        },
    }


# =============================================================================
# Reset (for testing)
# =============================================================================

def reset_metrics():
    """Reset all metrics (for testing purposes)."""
    for metric in ALL_METRICS:
        metric._values.clear()
