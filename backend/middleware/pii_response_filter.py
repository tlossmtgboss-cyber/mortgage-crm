"""
PII Response Filter Middleware

Two layers of PII protection for outbound API responses:

Layer 1 — Field-name masking (lightweight, O(keys) not O(bytes)):
    Parses JSON responses and masks values of known PII field names.
    Targeted fields: ssn, social_security_number, tax_id, bank_account_number,
    date_of_birth, dob.  Only touches fields by name — skips non-JSON and
    responses without matching keys.

Layer 2 — Regex safety-net (existing):
    Scans the full response body text for SSN / account-number patterns that
    may have leaked through a field with an unexpected name.

Masking formats:
    SSN / tax_id:        "***-**-1234"  (last 4 visible)
    bank_account_number: "****5678"     (last 4 visible)
    date_of_birth / dob: "**/**/1990"   (year only)

Header control:
    Masking is ON by default for all responses.
    To receive unmasked data, send `X-Mask-PII: false`.  This is only
    honoured for users whose JWT contains a platform_admin or site_admin role
    (determined from the Authorization header).  All other callers always
    receive masked data regardless of the header.

Configuration via environment variables:
    PII_RESPONSE_MODE   = "warn" | "mask" | "strict"   (default: "mask")
    PII_PORTAL_MASKING  = "true" | "false"              (default: "true")

Usage:
    from middleware.pii_response_filter import PIIResponseFilterMiddleware

    app.add_middleware(PIIResponseFilterMiddleware)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1 — Field-name masking configuration
# ---------------------------------------------------------------------------

# Field names (lowercase) whose values should be masked.
# Mapped to the masking function to apply.
_SSN_FIELDS: Set[str] = {
    "ssn",
    "social_security_number",
    "social_security",
    "ssn_number",
    "ssn_full",
    "full_ssn",
    "co_ssn",
    "co_ssn_encrypted",
    "ssn_encrypted",
}

_TAX_ID_FIELDS: Set[str] = {
    "tax_id",
    "tax_id_number",
    "tin",
    "ein",
    "fein",
    "employer_tax_id",
}

_ACCOUNT_FIELDS: Set[str] = {
    "bank_account_number",
    "account_number",
    "bank_account",
    "checking_account",
    "savings_account",
    "routing_number",
}

_DOB_FIELDS: Set[str] = {
    "date_of_birth",
    "dob",
    "birth_date",
    "birthdate",
    "borrower_dob",
    "co_borrower_dob",
}

# Roles allowed to bypass masking via X-Mask-PII: false
_ADMIN_ROLES: Set[str] = {"platform_admin", "site_admin"}


def _mask_ssn_value(value: Any) -> Any:
    """Mask SSN/tax-id style values: show last 4 digits only."""
    if not isinstance(value, str) or not value:
        return value
    # Already masked
    if value.startswith("***"):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) >= 4:
        return f"***-**-{digits[-4:]}"
    return "***-**-****"


def _mask_tax_id_value(value: Any) -> Any:
    """Mask tax ID values: show last 4 digits only."""
    if not isinstance(value, str) or not value:
        return value
    if value.startswith("***"):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) >= 4:
        return f"***-**-{digits[-4:]}"
    return "***-**-****"


def _mask_account_value(value: Any) -> Any:
    """Mask bank account numbers: show last 4 digits only."""
    if not isinstance(value, str) or not value:
        return value
    if value.startswith("****"):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) >= 4:
        return f"****{digits[-4:]}"
    return "********"


def _mask_dob_value(value: Any) -> Any:
    """Mask date of birth: show year only.

    Handles common formats:
      - MM/DD/YYYY  -> **/**/YYYY
      - YYYY-MM-DD  -> YYYY-**-**
      - ISO datetime -> YYYY-**-**T...
    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith("**"):
        return value
    # ISO format: 1990-05-14 or 1990-05-14T00:00:00
    iso_match = re.match(r"^(\d{4})-\d{2}-\d{2}(T.*)?$", value)
    if iso_match:
        suffix = iso_match.group(2) or ""
        return f"{iso_match.group(1)}-**-**{suffix}"
    # US format: 05/14/1990
    us_match = re.match(r"^\d{1,2}/\d{1,2}/(\d{4})$", value)
    if us_match:
        return f"**/**/{us_match.group(1)}"
    # Fallback: just return as-is if we can't parse
    return value


def _mask_fields_in_obj(obj: Any) -> Any:
    """Recursively walk a parsed JSON object and mask PII field values."""
    if isinstance(obj, dict):
        result = {}
        for key, val in obj.items():
            lower_key = key.lower()
            if lower_key in _SSN_FIELDS:
                result[key] = _mask_ssn_value(val)
            elif lower_key in _TAX_ID_FIELDS:
                result[key] = _mask_tax_id_value(val)
            elif lower_key in _ACCOUNT_FIELDS:
                result[key] = _mask_account_value(val)
            elif lower_key in _DOB_FIELDS:
                result[key] = _mask_dob_value(val)
            else:
                result[key] = _mask_fields_in_obj(val)
        return result
    elif isinstance(obj, list):
        return [_mask_fields_in_obj(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Layer 2 — Regex safety-net patterns (compiled once at import time)
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

# Patterns used for masking in portal responses and regex safety-net
_MASK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # SSN: keep last 4
    (
        re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b"),
        r"***-**-\3",
    ),
    # Account numbers (keyword-anchored)
    (
        re.compile(r'(?i)(account[_\s#:"]*)\d{4,13}(\d{4})'),
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

# Paths where field-level masking should be skipped entirely (health checks, etc.)
_SKIP_PATHS = (
    "/health",
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Max response body size to process (skip huge payloads to avoid latency)
_MAX_BODY_SIZE = 5 * 1024 * 1024  # 5 MB


def _extract_role_from_request(request: Request) -> Optional[str]:
    """Extract user role from a signature-verified JWT in the Authorization header.

    Returns the role string if present, else None. Uses auth.tokens for
    proper cryptographic verification — never trust unverified claims.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    try:
        from auth.tokens import verify_token
        token_data = verify_token(token)
        if token_data is None:
            logger.warning(
                "PII filter: JWT signature verification failed — "
                "defaulting to masked mode for %s %s",
                request.method, request.url.path,
            )
            return None
        return getattr(token_data, "role", None) or getattr(token_data, "user_role", None)
    except ImportError:
        logger.warning("PII filter: auth.tokens not available — defaulting to masked mode")
        return None
    except Exception as e:
        logger.warning(
            "PII filter: JWT verification failed (%s) — defaulting to masked mode", e,
        )
        return None


def _should_mask(request: Request) -> bool:
    """Determine whether PII masking should be applied.

    Masking is ON by default. It is only disabled when ALL of:
      1. The request includes header `X-Mask-PII: false`
      2. The caller has a platform_admin or site_admin role (from JWT)
    """
    mask_header = request.headers.get("x-mask-pii", "").lower().strip()
    if mask_header == "false":
        role = _extract_role_from_request(request)
        if role is None:
            logger.warning(
                "PII filter: X-Mask-PII=false requested but role extraction "
                "failed — keeping PII masked (fail-closed) for %s %s",
                request.method, request.url.path,
            )
        elif role.lower() in _ADMIN_ROLES:
            return False
    return True


class PIIResponseFilterMiddleware(BaseHTTPMiddleware):
    """Middleware that masks PII fields and inspects response bodies for PII leaks."""

    def __init__(self, app, mode: str | None = None, **kwargs):
        super().__init__(app, **kwargs)
        # Explicit parameter overrides env var; env var default is "mask"
        self.mode = (mode or os.environ.get("PII_RESPONSE_MODE", "mask")).lower()
        self.portal_masking = os.environ.get(
            "PII_PORTAL_MASKING", "true"
        ).lower() in ("true", "1", "yes")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip paths that never contain PII
        if any(request.url.path.startswith(p) for p in _SKIP_PATHS):
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("PII filter: inner middleware exception on %s %s: %s",
                         request.method, request.url.path, exc, exc_info=True)
            raise

        # Streaming responses cannot be reliably filtered without buffering
        # the entire stream, which would defeat the purpose of streaming.
        # Log a warning so this is visible in audit and monitoring.
        if isinstance(response, StreamingResponse):
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                logger.warning(
                    "PII filter: StreamingResponse with JSON content-type on "
                    "%s %s — PII masking is bypassed for streaming responses. "
                    "Ensure the producing endpoint does not emit PII in streamed data.",
                    request.method, request.url.path,
                )
            return response

        # Only inspect JSON-like responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read body -- requires consuming the response stream
        body_bytes = b""
        try:
            async for chunk in response.body_iterator:  # type: ignore[union-attr]
                if isinstance(chunk, str):
                    body_bytes += chunk.encode("utf-8")
                else:
                    body_bytes += chunk
        except Exception as exc:
            logger.error("PII filter: body read failed on %s %s: %s",
                         request.method, request.url.path, exc, exc_info=True)
            return Response(
                content=b'{"detail":"Internal server error"}',
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )

        # Skip oversized payloads to avoid latency
        if len(body_bytes) > _MAX_BODY_SIZE:
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        body_text = body_bytes.decode("utf-8", errors="replace")

        apply_masking = _should_mask(request)

        # ---------------------------------------------------------------
        # Layer 1: Field-name masking (fast, targeted)
        # ---------------------------------------------------------------
        if apply_masking:
            try:
                parsed = json.loads(body_text)
                masked = _mask_fields_in_obj(parsed)
                body_text = json.dumps(masked, ensure_ascii=False)
                body_bytes = body_text.encode("utf-8")
            except (json.JSONDecodeError, TypeError, ValueError):
                # Not valid JSON — fall through to regex layer
                pass

        # ---------------------------------------------------------------
        # Layer 2: Regex safety-net scan
        # ---------------------------------------------------------------
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
