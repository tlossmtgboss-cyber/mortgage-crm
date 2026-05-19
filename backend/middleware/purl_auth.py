"""
PURL Authentication Middleware

Provides authentication and authorization for PURL borrower portal endpoints:
- Token extraction from Authorization header
- Token verification using PURLTokenService
- Scope-based authorization
- Audit logging for PURL requests
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import Header, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from services.purl_token_service import PURLTokenService
from models.purl import TokenScope, PURLAuditLog, ActorType

logger = logging.getLogger(__name__)


# Security scheme for PURL tokens
purl_security = HTTPBearer(
    scheme_name="PURL Token",
    description="PURL access token for borrower portal",
    auto_error=False
)


class PURLAuthContext:
    """Context object containing PURL authentication information."""

    def __init__(
        self,
        token_id: int,
        organization_id: int,
        workspace_id: int,
        workspace_slug: str,
        workspace_status: str,
        scope: TokenScope,
        contact_id: Optional[int] = None
    ):
        self.token_id = token_id
        self.organization_id = organization_id
        self.workspace_id = workspace_id
        self.workspace_slug = workspace_slug
        self.workspace_status = workspace_status
        self.scope = scope
        self.contact_id = contact_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "token_id": self.token_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "workspace_slug": self.workspace_slug,
            "workspace_status": self.workspace_status,
            "scope": self.scope.value,
            "contact_id": self.contact_id
        }

    def has_write_access(self) -> bool:
        """Check if context has write access."""
        return self.scope in [TokenScope.WRITE, TokenScope.FULL, TokenScope.VOICE_REVIEW_SUBMIT]

    def has_full_access(self) -> bool:
        """Check if context has full access."""
        return self.scope == TokenScope.FULL


async def get_purl_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(purl_security),
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """
    Extract PURL token from request.

    Supports both:
    - HTTPBearer security scheme
    - Raw Authorization header with "Bearer" prefix
    """
    # Try HTTPBearer credentials first
    if credentials and credentials.credentials:
        token = credentials.credentials
        if token.startswith("purl_live_"):
            return token

    # Fallback to raw header
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]  # Remove "Bearer " prefix
            if token.startswith("purl_live_"):
                return token

    # Diagnostic: distinguish "header missing" from "header present but wrong scheme".
    # Without this it's nearly impossible to tell a stripped-by-proxy header apart
    # from a borrower who hit a PURL endpoint with a non-PURL JWT.
    if not credentials and not authorization:
        logger.debug("PURL token extraction: no Authorization header on request")
    else:
        cred_prefix = credentials.credentials[:10] if credentials and credentials.credentials else None
        hdr_prefix = authorization[:20] if authorization else None
        logger.warning(
            "PURL token extraction failed: scheme/prefix mismatch (credentials_prefix=%r, header_prefix=%r)",
            cred_prefix,
            hdr_prefix,
        )
    return None


async def get_purl_context_optional(
    request: Request,
    token: Optional[str] = Depends(get_purl_token),
    db: Session = Depends(get_db)
) -> Optional[PURLAuthContext]:
    """
    Get PURL authentication context if token is present.
    Returns None if no token or invalid token.
    Does NOT raise exceptions.
    """
    if not token:
        return None

    # Dev-mode test token bypass — requires explicit opt-in AND non-production
    import os
    if (
        token == "purl_live_dev_test_token_00000000"
        and os.getenv("ENVIRONMENT", "development") != "production"
        and os.getenv("ALLOW_TEST_TOKENS", "").lower() == "true"
    ):
        logger.info("Dev-mode PURL token accepted")
        return PURLAuthContext(
            token_id=0,
            organization_id=1,
            workspace_id=1,
            workspace_slug="dev-test",
            workspace_status="active",
            scope=TokenScope.WRITE,
            contact_id=9999,
        )

    try:
        token_service = PURLTokenService(db)
        context_data = token_service.verify_token(token)

        if not context_data:
            return None

        return PURLAuthContext(
            token_id=context_data["token_id"],
            organization_id=context_data["organization_id"],
            workspace_id=context_data["workspace_id"],
            workspace_slug=context_data["workspace_slug"],
            workspace_status=context_data["workspace_status"],
            scope=context_data["scope"],
            contact_id=context_data.get("contact_id")
        )

    except Exception as e:
        logger.warning(f"PURL token verification failed: {e}")
        return None


async def require_purl_token(
    request: Request,
    context: Optional[PURLAuthContext] = Depends(get_purl_context_optional)
) -> PURLAuthContext:
    """
    Require valid PURL token.
    Raises 401 if token is missing or invalid.
    """
    if not context:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing PURL access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Store context in request state for audit logging
    request.state.purl_context = context

    return context


async def require_purl_write_scope(
    context: PURLAuthContext = Depends(require_purl_token)
) -> PURLAuthContext:
    """
    Require PURL token with write or full scope.
    Raises 403 if scope is read-only.
    """
    if not context.has_write_access():
        raise HTTPException(
            status_code=403,
            detail="This action requires write access. Your token has read-only access."
        )

    return context


async def require_purl_full_scope(
    context: PURLAuthContext = Depends(require_purl_token)
) -> PURLAuthContext:
    """
    Require PURL token with full scope.
    Raises 403 if scope is not full.
    """
    if not context.has_full_access():
        raise HTTPException(
            status_code=403,
            detail="This action requires full access."
        )

    return context


def verify_workspace_access(
    context: PURLAuthContext,
    requested_slug: str
) -> bool:
    """
    Verify that context has access to requested workspace.

    Args:
        context: PURL authentication context
        requested_slug: Requested workspace slug from URL

    Returns:
        True if access is allowed

    Raises:
        HTTPException: If access is denied
    """
    if context.workspace_slug != requested_slug:
        raise HTTPException(
            status_code=403,
            detail="Access denied to this workspace"
        )

    return True


async def log_purl_action(
    db: Session,
    context: PURLAuthContext,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    changes: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None
):
    """
    Log a PURL action to the audit log.

    Args:
        db: Database session
        context: PURL authentication context
        action: Action performed
        resource_type: Type of resource affected
        resource_id: ID of resource affected
        changes: Changes made (for updates)
        metadata: Additional metadata
        ip_address: Client IP address
        user_agent: Client user agent
        request_id: Request ID for correlation
    """
    audit_entry = PURLAuditLog(
        organization_id=context.organization_id,
        actor_type=ActorType.CONTACT.value if context.contact_id else ActorType.API.value,
        actor_id=context.contact_id,
        workspace_id=context.workspace_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id
    )

    db.add(audit_entry)
    # Note: Don't commit here - let the route handler manage the transaction


class PURLAuditMiddleware:
    """
    Middleware for automatic PURL request auditing.
    Logs all authenticated PURL requests.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check if this is a PURL route
        path = scope.get("path", "")
        if not path.startswith("/api/purl/"):
            await self.app(scope, receive, send)
            return

        # Create request object to access headers
        from starlette.requests import Request
        request = Request(scope, receive)

        # Store start time
        start_time = datetime.now(timezone.utc)

        # Process request
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Store status code
                request.state.response_status = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Log audit entry after response
        try:
            if hasattr(request.state, "purl_context"):
                context = request.state.purl_context
                status_code = getattr(request.state, "response_status", 0)

                # Get database session
                from database import SessionLocal
                db = SessionLocal()

                try:
                    await log_purl_action(
                        db=db,
                        context=context,
                        action=f"{request.method} {path}",
                        resource_type="api_request",
                        metadata={
                            "status_code": status_code,
                            "duration_ms": (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                        },
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent")
                    )
                    db.commit()
                except Exception as e:
                    logger.exception(f"Failed to log PURL action and commit: {e}")
                    db.rollback()
                    raise
                finally:
                    db.close()

        except Exception as e:
            logger.error(f"Failed to log PURL audit: {e}")


# Rate limiting for PURL endpoints
class PURLRateLimiter:
    """
    Simple in-memory rate limiter for PURL endpoints.
    For production, consider using Redis-based rate limiting.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._minute_counters: Dict[str, list] = {}
        self._hour_counters: Dict[str, list] = {}

    def _get_identifier(self, context: PURLAuthContext) -> str:
        """Get rate limit identifier from context."""
        return f"token:{context.token_id}"

    def check_rate_limit(self, context: PURLAuthContext) -> bool:
        """
        Check if request is within rate limits.

        Returns:
            True if allowed, False if rate limited
        """
        import time

        identifier = self._get_identifier(context)
        now = time.time()

        # Clean up old entries
        minute_ago = now - 60
        hour_ago = now - 3600

        # Minute check
        if identifier not in self._minute_counters:
            self._minute_counters[identifier] = []
        self._minute_counters[identifier] = [
            t for t in self._minute_counters[identifier] if t > minute_ago
        ]

        if len(self._minute_counters[identifier]) >= self.requests_per_minute:
            return False

        # Hour check
        if identifier not in self._hour_counters:
            self._hour_counters[identifier] = []
        self._hour_counters[identifier] = [
            t for t in self._hour_counters[identifier] if t > hour_ago
        ]

        if len(self._hour_counters[identifier]) >= self.requests_per_hour:
            return False

        # Record request
        self._minute_counters[identifier].append(now)
        self._hour_counters[identifier].append(now)

        return True


# Singleton rate limiter instance
_rate_limiter = PURLRateLimiter()


async def check_purl_rate_limit(
    context: PURLAuthContext = Depends(require_purl_token)
) -> PURLAuthContext:
    """
    Check rate limit for PURL request.
    Raises 429 if rate limit exceeded.
    """
    if not _rate_limiter.check_rate_limit(context):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )

    return context
