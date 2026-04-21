"""
05-audit-logs/middleware.py

Catches every mutating API call and records a breadcrumb event. Route-level
audit_event() calls remain the primary source — this middleware is defense
in depth for any route where the author forgot to add one.

Drop-in: backend/app/middleware/audit.py

Register in main.py BEFORE the routes:
    app.add_middleware(AuditMiddleware)
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.db import async_session_factory
from app.services.audit import audit_event

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths we don't need a breadcrumb for — they emit their own semantic events
EXEMPT_PATHS = (
    "/auth/",        # routes file already calls audit_event explicitly
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/webhooks/",    # inbound webhooks are logged separately by the webhook handler
)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Pass through non-mutating or exempt paths without audit write
        path = request.url.path
        if request.method not in MUTATING_METHODS or path.startswith(EXEMPT_PATHS):
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response

        response = await call_next(request)

        # Write breadcrumb in a new session so we don't interfere with route tx
        try:
            async with async_session_factory() as session:
                actor = getattr(request.state, "user", None)

                # 2xx = success, 4xx client error = denied/failure, 5xx = failure
                if 200 <= response.status_code < 300:
                    outcome = "success"
                elif response.status_code in (401, 403):
                    outcome = "denied"
                else:
                    outcome = "failure"

                await audit_event(
                    session,
                    event_type=f"API_{request.method}_{_normalize_path(path)}",
                    outcome=outcome,
                    actor_id=getattr(actor, "id", None) if actor else None,
                    actor_email=getattr(actor, "email", None) if actor else None,
                    actor_role=getattr(actor, "role", None) if actor else None,
                    org_id=getattr(actor, "org_id", None) if actor else None,
                    ip=_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                    request_id=request_id,
                    metadata={
                        "method": request.method,
                        "path": path,
                        "status": response.status_code,
                        "query": dict(request.query_params),
                    },
                )
                await session.commit()
        except Exception as e:
            logger.exception("Audit middleware failed: %s", e)

        response.headers["x-request-id"] = request_id
        return response


def _normalize_path(path: str) -> str:
    """
    Turn /api/loans/550e8400-e29b-41d4-a716-446655440000/stage
    into /api/loans/:id/stage for useful grouping.
    """
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        # UUID or numeric ID → placeholder
        try:
            uuid.UUID(part)
            normalized.append(":id")
            continue
        except ValueError:
            pass
        if part.isdigit():
            normalized.append(":id")
            continue
        normalized.append(part)
    return "/" + "/".join(normalized)


def _client_ip(request: Request) -> str | None:
    # Railway / Cloudflare / load balancers
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None
