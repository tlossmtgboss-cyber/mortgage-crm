"""
Audit Middleware — Automatic request/response audit logging.
SOC 2 Criteria: CC4 (Monitoring), CC2 (Communication)

Automatically captures all API requests and responses in the audit log.
Uses the app's sync SQLAlchemy sessions via a background thread to avoid
blocking the request pipeline.
"""
import atexit
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy import text

from ..constants import AuditAction, SeverityLevel, AUDIT_EXCLUDE_PATHS, WRITE_METHODS

logger = logging.getLogger("soc2.middleware.audit")

# Thread pool for background audit log writes — ensures graceful shutdown
_audit_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="soc2-audit")
atexit.register(_audit_pool.shutdown, wait=True, cancel_futures=False)


def _write_audit_log_bg(
    user_id, user_email, user_role, tenant_id,
    action, method, path, request_id, ip, user_agent,
    status_code, success, severity, description
):
    """Write audit log entry in a background thread using a fresh sync session."""
    try:
        from db import SessionLocal
        session = SessionLocal()
        try:
            session.execute(
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
                        :request_id, CAST(NULLIF(:ip, '') AS INET), :user_agent,
                        :status_code, :success, :severity,
                        :description
                    )
                """),
                {
                    "user_id": str(user_id) if user_id else None,
                    "user_email": user_email,
                    "user_role": user_role,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "action": action.value if hasattr(action, 'value') else str(action),
                    "method": method,
                    "path": path,
                    "request_id": request_id,
                    "ip": ip,
                    "user_agent": user_agent,
                    "status_code": status_code,
                    "success": success,
                    "severity": severity.value if hasattr(severity, 'value') else str(severity),
                    "description": description,
                }
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Audit log write failed: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Audit middleware DB unavailable: {e}")


class AuditMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that automatically logs all API requests to the audit trail.

    Captures:
    - Request method, path, IP, user agent
    - Authenticated user (from request state, set by TenantContextMiddleware)
    - Response status code
    - Request duration
    - Correlation ID (request_id)

    Add to FastAPI:
        app.add_middleware(AuditMiddleware)
    """

    def __init__(self, app):
        super().__init__(app)
        self._table_exists: Optional[bool] = None  # checked once on first request

    def _check_table_exists(self) -> bool:
        """One-time check whether soc2_audit_log table exists."""
        try:
            from db import SessionLocal
            session = SessionLocal()
            try:
                session.execute(text("SELECT 1 FROM soc2_audit_log LIMIT 0"))
                return True
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                session.rollback()
                return False
            finally:
                session.close()
        except Exception as _exc:  # noqa: BLE001
            return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip excluded paths
        if request.url.path in AUDIT_EXCLUDE_PATHS:
            return await call_next(request)

        # One-time check: if soc2_audit_log table doesn't exist, pass through
        if self._table_exists is None:
            self._table_exists = self._check_table_exists()
            if not self._table_exists:
                logger.warning("soc2_audit_log table not found — audit middleware disabled")
        if not self._table_exists:
            return await call_next(request)

        # Generate correlation ID
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Capture timing
        start_time = time.time()

        # Process request
        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Extract user info from request state (set by TenantContextMiddleware)
        user_id = getattr(request.state, "user_id", None)
        user_email = getattr(request.state, "user_email", None)
        user_role = getattr(request.state, "user_role", None)
        tenant_id = (
            getattr(request.state, "tenant_id", None)
            or getattr(request.state, "organization_id", None)
        )

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

        ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")
        description = f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.0f}ms)"

        # Log to database in a background thread pool to avoid blocking
        _audit_pool.submit(
            _write_audit_log_bg,
            user_id, user_email, user_role, tenant_id,
            action, request.method, request.url.path,
            request_id, ip, user_agent,
            response.status_code, success, severity, description,
        )

        # NOTE: Do NOT modify response headers here — other middlewares
        # (request_context, structured_logging) already set X-Request-Id
        # and X-Response-Time. Duplicate header writes from stacked
        # BaseHTTPMiddleware cause h11 Content-Length corruption.

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

        # Special path-based overrides (match final path segment to avoid false positives)
        path_tail = path.rstrip("/").rsplit("/", 1)[-1]
        if path_tail in ("login", "token"):
            return AuditAction.LOGIN
        if path_tail == "logout":
            return AuditAction.LOGOUT
        if path_tail == "export":
            return AuditAction.DATA_EXPORT

        return method_action_map.get(method, AuditAction.READ)
