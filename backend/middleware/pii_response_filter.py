"""
PII Response Filter Middleware

Scans outbound API response bodies for PII patterns. Depending on
configuration, it either:
  - Logs a warning when PII is detected (warn-only mode, default)
  - Automatically masks SSN and account numbers in portal responses
  - Blocks the response entirely (strict mode -- returns 500)

Designed for Smart Docs V2 but applied globally so any accidental PII
leak from any endpoint is caught.

Configuration via environment variables:
    PII_RESPONSE_MODE   = "warn" | "mask" | "strict"   (default: "warn")
    PII_PORTAL_MASKING  = "true" | "false"              (default: "true")

Usage:
    from middleware.pii_response_filter import PIIResponseFilterMiddleware

    app.add_middleware(PIIResponseFilterMiddleware)
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns (compiled once at import time)
# ---------------------------------------------------------------------------

_PII_SCAN_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    # Full SSN: 123-45-6789
    (
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "***-**-XXXX",
    ),
    # SSN without hyphens (9 consecutive digits, heuristic)
    (
        "SSN_NOHYPHEN",
        re.compile(r'(?<=[":, ])\d{9}(?=[":, })\\])'),
        "***-**-XXXX",
    ),
    # Account numbers preceded by keyword
    (
        "ACCOUNT",
        re.compile(r'(?i)(account[_\s#:"]*)\d{8,17}'),
        r"\g<1>****XXXX",
    ),
]

# Patterns used for masking in portal responses
_MASK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # SSN: keep last 4
    (
        re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b"),
        r"***-**-\3",
    ),
    # Account numbers (keyword-anchored)
    (
        re.compile(r"(?i)(account[_\s#:\"]*)\d{4,13}(\d{4})"),
        r"\g<1>****\2",
    ),
]

# Portal path prefixes where automatic masking is applied
_PORTAL_PREFIXES = (
    "/api/v1/portal/",
    "/api/v1/borrower-portal/",
    "/api/v1/client-portal/",
    "/api/v1/realtor-portal/",
)


class PIIResponseFilterMiddleware(BaseHTTPMiddleware):
    """Middleware that inspects response bodies for PII leaks."""

    def __init__(self, app, mode: str | None = None, **kwargs):
        super().__init__(app, **kwargs)
        # Explicit parameter overrides env var; env var default is "warn"
        self.mode = (mode or os.environ.get("PII_RESPONSE_MODE", "warn")).lower()
        self.portal_masking = os.environ.get(
            "PII_PORTAL_MASKING", "true"
        ).lower() in ("true", "1", "yes")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Only inspect JSON-like responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read body -- requires consuming the response stream
        body_bytes = b""
        async for chunk in response.body_iterator:  # type: ignore[union-attr]
            if isinstance(chunk, str):
                body_bytes += chunk.encode("utf-8")
            else:
                body_bytes += chunk

        body_text = body_bytes.decode("utf-8", errors="replace")

        # Detect PII
        detections = self._scan(body_text)

        is_portal = any(
            request.url.path.startswith(prefix) for prefix in _PORTAL_PREFIXES
        )

        if detections:
            path = request.url.path
            method = request.method
            det_types = ", ".join(sorted({d[0] for d in detections}))
            count = len(detections)

            if self.mode == "strict":
                logger.error(
                    "PII leak BLOCKED: %s %s -- %d detection(s): %s",
                    method, path, count, det_types,
                )
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Response blocked by PII filter",
                    },
                )

            # Log the detection
            logger.warning(
                "PII detected in response: %s %s -- %d detection(s): %s",
                method, path, count, det_types,
            )

            # In "mask" mode, mask ALL responses with detected PII.
            # In "warn" mode, only auto-mask portal responses if enabled.
            if self.mode == "mask" or (is_portal and self.portal_masking):
                body_text = self._mask(body_text)
                body_bytes = body_text.encode("utf-8")

        # Rebuild response with (possibly modified) body
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    @staticmethod
    def _scan(text: str) -> List[Tuple[str, int]]:
        """Return list of (pii_type, match_position) tuples."""
        results = []
        for pii_type, pattern, _mask in _PII_SCAN_PATTERNS:
            for match in pattern.finditer(text):
                results.append((pii_type, match.start()))
        return results

    @staticmethod
    def _mask(text: str) -> str:
        """Apply masking patterns to the response text."""
        for pattern, replacement in _MASK_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
