"""
Audit Middleware — SOC 2 Breadcrumb Coverage

Catches every mutating API call and records a breadcrumb event. Route-level
audit_event() calls remain the primary source — this middleware is defense
in depth for any route where the author forgot to add one.

Register in main.py:
    app.add_middleware(AuditMiddleware)
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

EXEMPT_PATHS = (
    "/auth/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/webhooks/",
    "/api/v1/telnyx/",
    "/api/v1/vapi/",
)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        path = request.url.path
        if request.method not in MUTATING_METHODS or path.startswith(EXEMPT_PATHS):
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response

        response = await call_next(request)

        try:
            from db import SessionLocal
            from services.audit_events import audit_event

            db = SessionLocal()
            try:
                actor = getattr(request.state, "user", None)

                if 200 <= response.status_code < 300:
                    outcome = "success"
                elif response.status_code in (401, 403):
                    outcome = "denied"
                else:
                    outcome = "failure"

                audit_event(
                    db,
                    event_type=f"API_{request.method}_{_normalize_path(path)}",
                    outcome=outcome,
                    actor_id=getattr(actor, "id", None) if actor else None,
                    actor_email=getattr(actor, "email", None) if actor else None,
                    actor_role=getattr(actor, "role", None) if actor else None,
                    org_id=getattr(actor, "organization_id", None) if actor else None,
                    ip=_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                    request_id=request_id,
                    metadata={
                        "method": request.method,
                        "path": path,
                        "status": response.status_code,
                    },
                )
                db.commit()
            except Exception as e:
                logger.exception("Audit middleware failed: %s", e)
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.warning("Audit middleware import failed: %s", e)

        response.headers["x-request-id"] = request_id
        return response


def _normalize_path(path: str) -> str:
    """Turn /api/loans/550e8400-.../stage into /api/loans/:id/stage"""
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
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


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
