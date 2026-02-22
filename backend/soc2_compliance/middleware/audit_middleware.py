"""
Audit Middleware — Automatic request/response audit logging.
SOC 2 Criteria: CC4 (Monitoring), CC2 (Communication)

Automatically captures all API requests and responses in the audit log.
Integrates with FastAPI's middleware system.
"""
import logging
import time
from typing import Optional
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy import text

from ..constants import AuditAction, SeverityLevel, AUDIT_EXCLUDE_PATHS, WRITE_METHODS

logger = logging.getLogger("soc2.middleware.audit")


class AuditMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that automatically logs all API requests to the audit trail.
    
    Captures:
    - Request method, path, IP, user agent
    - Authenticated user (from request state)
    - Response status code
    - Request duration
    - Correlation ID (request_id)
    
    Add to FastAPI:
        app.add_middleware(AuditMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip excluded paths
        if request.url.path in AUDIT_EXCLUDE_PATHS:
            return await call_next(request)

        # Generate correlation ID
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Capture timing
        start_time = time.time()

        # Process request
        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Extract user info from request state (set by your auth middleware)
        user_id = getattr(request.state, "user_id", None)
        user_email = getattr(request.state, "user_email", None)
        user_role = getattr(request.state, "user_role", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Determine action type
        action = self._determine_action(request.method, request.url.path)

        # Determine severity based on response code
        severity = SeverityLevel.LOW
        success = 200 <= response.status_code < 400

        if response.status_code >= 500:
            severity = SeverityLevel.HIGH
        elif response.status_code in (401, 403):
            severity = SeverityLevel.MEDIUM
        elif request.method in WRITE_METHODS:
            severity = SeverityLevel.MEDIUM if not success else SeverityLevel.LOW

        # Log to database asynchronously
        try:
            # Get DB session from app state
            # NOTE: Adapt this to your DB session management
            db = getattr(request.app.state, "db_session_factory", None)
            if db:
                async with db() as session:
                    await session.execute(
                        text("""
                            INSERT INTO soc2_audit_log (
                                timestamp, user_id, user_email, user_role, tenant_id,
                                action, request_method, request_path,
                                request_id, ip_address, user_agent,
                                status_code, success, severity,
                                description
                            ) VALUES (
                                NOW(), :user_id, :user_email, :user_role, :tenant_id,
                                :action, :method, :path,
                                :request_id, :ip::inet, :user_agent,
                                :status_code, :success, :severity,
                                :description
                            )
                        """),
                        {
                            "user_id": str(user_id) if user_id else None,
                            "user_email": user_email,
                            "user_role": user_role,
                            "tenant_id": str(tenant_id) if tenant_id else None,
                            "action": action,
                            "method": request.method,
                            "path": request.url.path,
                            "request_id": request_id,
                            "ip": request.client.host if request.client else None,
                            "user_agent": request.headers.get("user-agent", ""),
                            "status_code": response.status_code,
                            "success": success,
                            "severity": severity,
                            "description": f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.0f}ms)",
                        }
                    )
                    await session.commit()
        except Exception as e:
            # Never let audit logging break the request
            logger.error(f"Audit middleware logging failed: {e}")

        # Add correlation headers to response
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        return response

    def _determine_action(self, method: str, path: str) -> str:
        """Map HTTP method + path to an audit action."""
        method_action_map = {
            "GET": AuditAction.READ,
            "POST": AuditAction.CREATE,
            "PUT": AuditAction.UPDATE,
            "PATCH": AuditAction.UPDATE,
            "DELETE": AuditAction.DELETE,
        }

        # Special path-based overrides
        if "/login" in path or "/auth" in path:
            return AuditAction.LOGIN
        if "/logout" in path:
            return AuditAction.LOGOUT
        if "/export" in path:
            return AuditAction.DATA_EXPORT

        return method_action_map.get(method, AuditAction.READ)
