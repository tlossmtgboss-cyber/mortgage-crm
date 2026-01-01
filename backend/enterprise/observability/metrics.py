"""
Business Metrics Collection Service

Provides metrics collection for:
- Technical metrics (latency, throughput, errors)
- Business KPIs (loan volume, conversion rates)
- SLI/SLO monitoring
- Custom application metrics

Enterprise Features:
- Prometheus-compatible metrics
- Business KPI dashboards
- SLI/SLO tracking
- Anomaly detection
- Multi-dimensional metrics
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """A single metric value with labels"""
    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    help_text: str = ""


class Counter:
    """Counter metric - only increases"""

    def __init__(self, name: str, help_text: str = "", labels: List[str] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1, **labels):
        """Increment counter"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += value

    def get(self, **labels) -> float:
        """Get current value"""
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0)

    def collect(self) -> List[MetricValue]:
        """Collect all values"""
        values = []
        with self._lock:
            for labels_tuple, value in self._values.items():
                labels = dict(labels_tuple)
                values.append(MetricValue(
                    name=self.name,
                    value=value,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                    help_text=self.help_text,
                ))
        return values


class Gauge:
    """Gauge metric - can increase or decrease"""

    def __init__(self, name: str, help_text: str = "", labels: List[str] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels):
        """Set gauge value"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = value

    def inc(self, value: float = 1, **labels):
        """Increment gauge"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def dec(self, value: float = 1, **labels):
        """Decrement gauge"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0) - value

    def get(self, **labels) -> float:
        """Get current value"""
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0)

    def collect(self) -> List[MetricValue]:
        """Collect all values"""
        values = []
        with self._lock:
            for labels_tuple, value in self._values.items():
                labels = dict(labels_tuple)
                values.append(MetricValue(
                    name=self.name,
                    value=value,
                    metric_type=MetricType.GAUGE,
                    labels=labels,
                    help_text=self.help_text,
                ))
        return values


class Histogram:
    """Histogram metric for distribution tracking"""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        help_text: str = "",
        labels: List[str] = None,
        buckets: tuple = None,
    ):
        self.name = name
        self.help_text = help_text
        self.label_names = labels or []
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: Dict[tuple, Dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._totals: Dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels):
        """Record a value"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._sums[key] += value
            self._totals[key] += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[key][bucket] += 1

    def time(self, **labels):
        """Context manager for timing"""
        return _HistogramTimer(self, labels)

    def collect(self) -> List[MetricValue]:
        """Collect all values"""
        values = []
        with self._lock:
            for labels_tuple, bucket_counts in self._counts.items():
                labels = dict(labels_tuple)

                # Bucket values
                cumulative = 0
                for bucket in self.buckets:
                    cumulative += bucket_counts.get(bucket, 0)
                    bucket_labels = {**labels, "le": str(bucket)}
                    values.append(MetricValue(
                        name=f"{self.name}_bucket",
                        value=cumulative,
                        metric_type=MetricType.HISTOGRAM,
                        labels=bucket_labels,
                        help_text=self.help_text,
                    ))

                # +Inf bucket
                inf_labels = {**labels, "le": "+Inf"}
                values.append(MetricValue(
                    name=f"{self.name}_bucket",
                    value=self._totals[labels_tuple],
                    metric_type=MetricType.HISTOGRAM,
                    labels=inf_labels,
                ))

                # Sum and count
                values.append(MetricValue(
                    name=f"{self.name}_sum",
                    value=self._sums[labels_tuple],
                    metric_type=MetricType.HISTOGRAM,
                    labels=labels,
                ))
                values.append(MetricValue(
                    name=f"{self.name}_count",
                    value=self._totals[labels_tuple],
                    metric_type=MetricType.HISTOGRAM,
                    labels=labels,
                ))

        return values


class _HistogramTimer:
    """Timer context manager for histogram"""

    def __init__(self, histogram: Histogram, labels: dict):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.histogram.observe(duration, **self.labels)


class MetricsCollector:
    """
    Centralized metrics collection.

    Provides Prometheus-compatible metrics export.
    """

    def __init__(self, service_name: str = "mortgage-crm"):
        self.service_name = service_name
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()

        # Register default metrics
        self._register_default_metrics()

    def _register_default_metrics(self):
        """Register default application metrics"""
        # Request metrics
        self.register(Counter(
            "http_requests_total",
            "Total HTTP requests",
            labels=["method", "path", "status"],
        ))

        self.register(Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            labels=["method", "path"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        ))

        # Error metrics
        self.register(Counter(
            "errors_total",
            "Total errors",
            labels=["type", "component"],
        ))

        # Active connections
        self.register(Gauge(
            "active_connections",
            "Active connections",
            labels=["type"],
        ))

    def register(self, metric):
        """Register a metric"""
        with self._lock:
            self._metrics[metric.name] = metric
        return metric

    def get(self, name: str):
        """Get a metric by name"""
        return self._metrics.get(name)

    def counter(self, name: str, help_text: str = "", labels: List[str] = None) -> Counter:
        """Create or get a counter"""
        if name not in self._metrics:
            self.register(Counter(name, help_text, labels))
        return self._metrics[name]

    def gauge(self, name: str, help_text: str = "", labels: List[str] = None) -> Gauge:
        """Create or get a gauge"""
        if name not in self._metrics:
            self.register(Gauge(name, help_text, labels))
        return self._metrics[name]

    def histogram(
        self,
        name: str,
        help_text: str = "",
        labels: List[str] = None,
        buckets: tuple = None,
    ) -> Histogram:
        """Create or get a histogram"""
        if name not in self._metrics:
            self.register(Histogram(name, help_text, labels, buckets))
        return self._metrics[name]

    def collect_all(self) -> List[MetricValue]:
        """Collect all metrics"""
        values = []
        with self._lock:
            for metric in self._metrics.values():
                values.extend(metric.collect())
        return values

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        values = self.collect_all()

        # Group by metric name
        by_name = defaultdict(list)
        for value in values:
            by_name[value.name].append(value)

        for name, metric_values in by_name.items():
            # Help text
            if metric_values[0].help_text:
                lines.append(f"# HELP {name} {metric_values[0].help_text}")

            # Type
            lines.append(f"# TYPE {name} {metric_values[0].metric_type.value}")

            # Values
            for mv in metric_values:
                if mv.labels:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in sorted(mv.labels.items()))
                    lines.append(f'{name}{{{labels_str}}} {mv.value}')
                else:
                    lines.append(f'{name} {mv.value}')

        return "\n".join(lines)


class BusinessMetrics:
    """
    Business-specific metrics for mortgage CRM.

    Tracks KPIs like loan volume, conversion rates, and SLAs.
    """

    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self._register_business_metrics()

    def _register_business_metrics(self):
        """Register business-specific metrics"""
        # Loan metrics
        self.collector.register(Counter(
            "loan_applications_total",
            "Total loan applications",
            labels=["loan_type", "source", "status"],
        ))

        self.collector.register(Gauge(
            "active_pipeline_value_dollars",
            "Current pipeline value in dollars",
            labels=["status", "loan_type"],
        ))

        self.collector.register(Gauge(
            "active_pipeline_count",
            "Number of loans in pipeline",
            labels=["status", "loan_type"],
        ))

        self.collector.register(Histogram(
            "loan_processing_time_days",
            "Time to process loans in days",
            labels=["loan_type"],
            buckets=(7, 14, 21, 30, 45, 60, 90),
        ))

        # Lead metrics
        self.collector.register(Counter(
            "leads_created_total",
            "Total leads created",
            labels=["source", "campaign"],
        ))

        self.collector.register(Counter(
            "leads_converted_total",
            "Total leads converted to applications",
            labels=["source"],
        ))

        self.collector.register(Gauge(
            "lead_conversion_rate",
            "Lead to application conversion rate",
            labels=["source"],
        ))

        # SLA metrics
        self.collector.register(Counter(
            "sla_breaches_total",
            "Total SLA breaches",
            labels=["sla_type", "severity"],
        ))

        self.collector.register(Histogram(
            "sla_response_time_hours",
            "Time to respond/complete SLA items",
            labels=["sla_type"],
            buckets=(1, 2, 4, 8, 24, 48, 72),
        ))

        # AI metrics
        self.collector.register(Counter(
            "ai_decisions_total",
            "Total AI decisions made",
            labels=["decision_type", "outcome"],
        ))

        self.collector.register(Histogram(
            "ai_inference_time_seconds",
            "AI model inference time",
            labels=["model"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        ))

    def record_loan_application(
        self,
        loan_type: str,
        source: str,
        status: str = "submitted",
    ):
        """Record a new loan application"""
        counter = self.collector.get("loan_applications_total")
        if counter:
            counter.inc(loan_type=loan_type, source=source, status=status)

    def update_pipeline_value(
        self,
        status: str,
        loan_type: str,
        value: float,
        count: int,
    ):
        """Update pipeline metrics"""
        value_gauge = self.collector.get("active_pipeline_value_dollars")
        count_gauge = self.collector.get("active_pipeline_count")

        if value_gauge:
            value_gauge.set(value, status=status, loan_type=loan_type)
        if count_gauge:
            count_gauge.set(count, status=status, loan_type=loan_type)

    def record_loan_processing_time(self, loan_type: str, days: float):
        """Record loan processing time"""
        histogram = self.collector.get("loan_processing_time_days")
        if histogram:
            histogram.observe(days, loan_type=loan_type)

    def record_lead_created(self, source: str, campaign: str = ""):
        """Record a new lead"""
        counter = self.collector.get("leads_created_total")
        if counter:
            counter.inc(source=source, campaign=campaign)

    def record_lead_conversion(self, source: str):
        """Record a lead conversion"""
        counter = self.collector.get("leads_converted_total")
        if counter:
            counter.inc(source=source)

    def record_sla_breach(self, sla_type: str, severity: str = "warning"):
        """Record an SLA breach"""
        counter = self.collector.get("sla_breaches_total")
        if counter:
            counter.inc(sla_type=sla_type, severity=severity)

    def record_ai_decision(self, decision_type: str, outcome: str):
        """Record an AI decision"""
        counter = self.collector.get("ai_decisions_total")
        if counter:
            counter.inc(decision_type=decision_type, outcome=outcome)

    def record_ai_inference_time(self, model: str, seconds: float):
        """Record AI inference time"""
        histogram = self.collector.get("ai_inference_time_seconds")
        if histogram:
            histogram.observe(seconds, model=model)


# FastAPI integration
def create_metrics_routes(collector: MetricsCollector):
    """
    Create FastAPI metrics routes.

    Usage:
        from fastapi import FastAPI
        from enterprise.observability.metrics import MetricsCollector, create_metrics_routes

        app = FastAPI()
        metrics = MetricsCollector()
        app.include_router(create_metrics_routes(metrics))
    """
    from fastapi import APIRouter, Response

    router = APIRouter(tags=["metrics"])

    @router.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(
            content=collector.to_prometheus(),
            media_type="text/plain",
        )

    return router
