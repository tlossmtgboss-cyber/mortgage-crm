"""
Smart Docs Metrics Middleware

FastAPI middleware that automatically records per-endpoint metrics:
- Request count
- Response time (added as X-Processing-Time-Ms header)
- Error count (4xx and 5xx responses)

Only instruments requests to Smart Docs API paths (/api/smart-docs/*
and /api/v1/smart-docs/*) to avoid overhead on unrelated routes.

Usage in main.py:
    from services.smart_docs.metrics_middleware import SmartDocsMetricsMiddleware
    app.add_middleware(SmartDocsMetricsMiddleware)
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from services.smart_docs.monitoring_service import get_metrics_collector

logger = logging.getLogger(__name__)

# Path prefixes to instrument
_INSTRUMENTED_PREFIXES = (
    "/api/smart-docs/",
    "/api/v1/smart-docs/",
    "/api/v1/esign/",
)

# Header name for processing time
PROCESSING_TIME_HEADER = "X-Processing-Time-Ms"


class SmartDocsMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records request-level metrics for Smart Docs endpoints.

    For each instrumented request, records:
    - An operation metric with the path and duration
    - Adds X-Processing-Time-Ms response header
    - Tracks error counts for 4xx/5xx responses
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Only instrument Smart Docs paths
        if not any(path.startswith(prefix) for prefix in _INSTRUMENTED_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        success = True
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            success = status_code < 400
        except Exception:
            success = False
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)

            # Record metric
            collector = get_metrics_collector()

            # Derive operation name from path
            operation_name = self._path_to_operation(path)

            collector.record(
                operation=f"http:{operation_name}",
                duration_ms=duration_ms,
                success=success,
                tags={
                    "method": request.method,
                    "path": path,
                    "status_code": str(status_code),
                },
            )

            if not success:
                collector.record_error(
                    operation=f"http:{operation_name}",
                    error_type=f"http_{status_code}",
                    error_message=f"{request.method} {path} returned {status_code}",
                )

        # Add timing header to response
        response.headers[PROCESSING_TIME_HEADER] = str(duration_ms)
        return response

    @staticmethod
    def _path_to_operation(path: str) -> str:
        """Convert a URL path to a short operation name for metrics.

        Examples:
            /api/smart-docs/doc-intel/classify -> doc-intel/classify
            /api/v1/smart-docs/documents/123 -> documents/{id}
        """
        # Strip known prefixes
        for prefix in _INSTRUMENTED_PREFIXES:
            if path.startswith(prefix):
                short = path[len(prefix):]
                break
        else:
            short = path

        # Replace numeric path segments with {id} to avoid cardinality explosion
        parts = short.rstrip("/").split("/")
        normalized = []
        for part in parts:
            if part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)

        return "/".join(normalized) if normalized else "root"
