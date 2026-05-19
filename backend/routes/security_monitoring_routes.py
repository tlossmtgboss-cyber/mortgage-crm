"""
Security Monitoring Routes - Admin Dashboard Security Endpoints

Provides real-time security monitoring data for the admin dashboard including:
- Rate limit status and violations
- Failed login attempts
- Blocked IPs
- Security event logs
- System health from security perspective
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import logging
import os

from database import get_db
from db import get_async_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/security", tags=["Security Monitoring"])

# Will be set by main.py
get_current_user = None


def set_dependencies(current_user_func):
    """Set dependencies from main.py to avoid circular imports."""
    global get_current_user
    get_current_user = current_user_func
    logger.info("Security monitoring routes dependencies set")


async def get_user_from_request(request: Request, db: Session):
    """Helper to extract token and get current user."""
    if get_current_user is None:
        raise HTTPException(status_code=500, detail="Security routes not properly initialized")
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = auth_header.replace('Bearer ', '')
    return await get_current_user(token, request, db)


async def require_admin_dep(request: Request):
    """Require admin role for security endpoints.

    Uses a dedicated short-lived sync session for auth, leaving route
    handlers free to use `get_async_db()` independently.
    """
    from database import SessionLocal
    local_db = SessionLocal()
    try:
        current_user = await get_user_from_request(request, local_db)
    finally:
        local_db.close()
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_role = getattr(current_user, 'role', '').lower()
    permission_role = getattr(current_user, 'permission_role', '').lower() if getattr(current_user, 'permission_role', None) else ''
    admin_roles = ('admin', 'superadmin', 'super_admin', 'system_admin', 'site_admin', 'master_admin')
    if user_role not in admin_roles and permission_role not in admin_roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user


@router.get("/dashboard")
async def get_security_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_dep)
):
    """
    Get comprehensive security dashboard data.
    Returns rate limiting stats, blocked IPs, failed logins, and security events.
    """
    try:
        # Access the middleware instances from the app state
        app = request.app

        # Get rate limit stats
        rate_limit_stats = _get_rate_limit_stats(app)

        # Get IP blocking stats
        ip_blocking_stats = _get_ip_blocking_stats(app)

        # Get security configuration
        security_config = _get_security_config()

        # Get recent security events from database (tenant-scoped)
        _user_org_id = getattr(current_user, 'organization_id', None)
        security_events = await _get_recent_security_events(db, org_id=_user_org_id)

        # Get failed login attempts (in-memory middleware data; db arg unused)
        failed_logins = _get_failed_login_stats(app, db)

        return {
            "status": "active",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": os.getenv("ENVIRONMENT", "development"),
            "rate_limiting": rate_limit_stats,
            "ip_blocking": ip_blocking_stats,
            "failed_logins": failed_logins,
            "security_events": security_events,
            "configuration": security_config,
            "middleware_status": {
                "ip_access_control": True,
                "rate_limiting": True,
                "security_headers": True,
                "ip_blocking": True,
                "request_validation": True,
                "security_logging": True,
                "impersonation_enforcement": True,
                "dynamic_cors": True
            }
        }
    except Exception as e:
        logger.exception("Error fetching security dashboard")
        raise HTTPException(status_code=500, detail="Error fetching security data")


@router.get("/rate-limits")
async def get_rate_limit_details(
    request: Request,
    current_user=Depends(require_admin_dep)
):
    """Get detailed rate limiting information."""
    try:
        app = request.app
        rate_limit_stats = _get_rate_limit_stats(app)

        return {
            "status": "active",
            "stats": rate_limit_stats,
            "tiers": {
                "admin": {"requests_per_minute": 500, "requests_per_hour": 20000},
                "power_user": {"requests_per_minute": 300, "requests_per_hour": 15000},
                "standard": {"requests_per_minute": 120, "requests_per_hour": 5000},
                "anonymous": {"requests_per_minute": 60, "requests_per_hour": 1000},
            },
            "endpoint_multipliers": {
                "/api/v1/ai/": 0.2,
                "/api/v1/chat/": 0.3,
                "/api/v1/blog/generate": 0.1,
                "/api/v1/documents/upload": 0.5,
                "/api/v1/smart-docs/upload": 0.5,
                "/api/v1/": 1.0,
            }
        }
    except Exception as e:
        logger.exception("Error fetching rate limit details")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/blocked-ips")
async def get_blocked_ips(
    request: Request,
    current_user=Depends(require_admin_dep)
):
    """Get list of currently blocked IPs."""
    try:
        app = request.app
        blocked_ips = []

        # Try to access IPBlockingMiddleware
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'blocked_ips'):
                blocked_ips = list(middleware.app.blocked_ips)
                break

        # Alternative: check app state
        if hasattr(app, 'state') and hasattr(app.state, 'blocked_ips'):
            blocked_ips = list(app.state.blocked_ips)

        return {
            "count": len(blocked_ips),
            "blocked_ips": blocked_ips,
            "note": "IPs are blocked for 15 minutes after 5 failed login attempts"
        }
    except Exception as e:
        logger.exception("Error fetching blocked IPs")
        return {
            "count": 0,
            "blocked_ips": [],
            "error": "Internal server error"
        }


@router.post("/unblock-ip/{ip_address}")
async def unblock_ip(
    ip_address: str,
    request: Request,
    current_user=Depends(require_admin_dep)
):
    """Manually unblock an IP address."""
    try:
        app = request.app
        unblocked = False

        # Try to access IPBlockingMiddleware
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'blocked_ips'):
                if ip_address in middleware.app.blocked_ips:
                    middleware.app.blocked_ips.discard(ip_address)
                    unblocked = True
                break

        if unblocked:
            logger.info(f"Admin {current_user.id} unblocked IP: {ip_address}")
            return {"status": "success", "message": f"IP {ip_address} has been unblocked"}
        else:
            return {"status": "not_found", "message": f"IP {ip_address} was not in blocked list"}

    except Exception as e:
        logger.exception(f"Error unblocking IP {ip_address}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/clear-rate-limit/{identifier}")
async def clear_rate_limit(
    identifier: str,
    request: Request,
    current_user=Depends(require_admin_dep)
):
    """Clear rate limit for a specific user or IP."""
    try:
        app = request.app
        cleared = False

        # Try to access RateLimitMiddleware
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'clear_rate_limit'):
                cleared = middleware.app.clear_rate_limit(identifier)
                break

        if cleared:
            logger.info(f"Admin {current_user.email} cleared rate limit for: {identifier}")
            return {"status": "success", "message": f"Rate limit cleared for {identifier}"}
        else:
            return {"status": "not_found", "message": f"No rate limit data found for {identifier}"}

    except Exception as e:
        logger.exception(f"Error clearing rate limit for {identifier}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/events")
async def get_security_events(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_admin_dep),
    limit: int = 100,
    event_type: Optional[str] = None
):
    """Get recent security events from audit log (tenant-scoped)."""
    try:
        _user_org_id = getattr(current_user, 'organization_id', None)
        events = await _get_recent_security_events(db, limit=limit, event_type=event_type, org_id=_user_org_id)
        return {
            "count": len(events),
            "events": events
        }
    except Exception as e:
        logger.exception("Error fetching security events")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def get_security_health(
    request: Request,
    current_user=Depends(require_admin_dep)
):
    """Get overall security system health status."""
    try:
        environment = os.getenv("ENVIRONMENT", "development")

        checks = {
            "environment": {
                "status": "ok" if environment in ("production", "staging", "development") else "warning",
                "value": environment
            },
            "secret_key": {
                "status": "ok" if os.getenv("SECRET_KEY") else "warning",
                "value": "configured" if os.getenv("SECRET_KEY") else "using default (insecure)"
            },
            "admin_ips": {
                "status": "ok" if any([os.getenv("ADMIN_IP_1"), os.getenv("ADMIN_IP_2"), os.getenv("ADMIN_IP_3")]) else "info",
                "value": "configured" if any([os.getenv("ADMIN_IP_1"), os.getenv("ADMIN_IP_2"), os.getenv("ADMIN_IP_3")]) else "not configured (using defaults)"
            },
            "test_api_key": {
                "status": "warning" if os.getenv("TEST_API_KEY") and environment == "production" else "ok",
                "value": "configured" if os.getenv("TEST_API_KEY") else "not configured"
            }
        }

        # Calculate overall health
        statuses = [c["status"] for c in checks.values()]
        if "error" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.exception("Error checking security health")
        raise HTTPException(status_code=500, detail="Internal server error")


# Helper functions

def _get_rate_limit_stats(app) -> Dict[str, Any]:
    """Extract rate limiting statistics from middleware."""
    stats = {
        "active_keys": 0,
        "total_requests_tracked": 0,
        "top_requesters": [],
        "recent_violations": []
    }

    try:
        # Try to find RateLimitMiddleware in the middleware stack
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'request_history'):
                history = middleware.app.request_history
                stats["active_keys"] = len(history)
                stats["total_requests_tracked"] = sum(len(v) for v in history.values())

                # Get top requesters
                top = sorted(
                    [(k, len(v)) for k, v in history.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
                stats["top_requesters"] = [{"key": k, "requests": c} for k, c in top]
                break
    except Exception as e:
        logger.debug(f"Could not extract rate limit stats: {e}")

    return stats


def _get_ip_blocking_stats(app) -> Dict[str, Any]:
    """Extract IP blocking statistics from middleware."""
    stats = {
        "blocked_count": 0,
        "blocked_ips": [],
        "failed_attempts_tracked": 0
    }

    try:
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'blocked_ips'):
                stats["blocked_count"] = len(middleware.app.blocked_ips)
                stats["blocked_ips"] = list(middleware.app.blocked_ips)[:20]  # Limit to first 20

                if hasattr(middleware.app, 'failed_attempts'):
                    stats["failed_attempts_tracked"] = len(middleware.app.failed_attempts)
                break
    except Exception as e:
        logger.debug(f"Could not extract IP blocking stats: {e}")

    return stats


def _get_security_config() -> Dict[str, Any]:
    """Get current security configuration."""
    return {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "whitelisted_ips_configured": any([
            os.getenv("ADMIN_IP_1"),
            os.getenv("ADMIN_IP_2"),
            os.getenv("ADMIN_IP_3")
        ]),
        "test_api_key_configured": bool(os.getenv("TEST_API_KEY")),
        "max_request_size_mb": 10,
        "failed_login_threshold": 5,
        "failed_login_window_minutes": 15,
        "rate_limit_tiers": ["admin", "power_user", "standard", "anonymous"]
    }


async def _get_recent_security_events(
    db: AsyncSession,
    limit: int = 50,
    event_type: Optional[str] = None,
    org_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Get recent security events from audit log, scoped to organization.

    Args:
        db: Database session
        limit: Max events to return
        event_type: Optional filter on event_type
        org_id: Organization ID for tenant scoping. When provided, only
                events belonging to this org are returned.
    """
    events = []

    try:
        # Try to query audit_logs table if it exists
        from sqlalchemy import text

        query = """
            SELECT id, event_type, user_id, ip_address, details, created_at
            FROM audit_logs
            WHERE (event_type LIKE '%security%'
               OR event_type LIKE '%login%'
               OR event_type LIKE '%auth%'
               OR event_type LIKE '%block%'
               OR event_type LIKE '%rate_limit%')
        """

        params: Dict[str, Any] = {"limit": limit}

        # Tenant scoping — only return events for this organization
        if org_id is not None:
            query += " AND (organization_id = :org_id OR organization_id IS NULL)"
            params["org_id"] = org_id

        if event_type:
            query += " AND event_type = :event_type"
            params["event_type"] = event_type

        query += " ORDER BY created_at DESC LIMIT :limit"

        result = await db.execute(text(query), params)

        for row in result:
            events.append({
                "id": row[0],
                "event_type": row[1],
                "user_id": row[2],
                "ip_address": row[3],
                "details": row[4],
                "created_at": row[5].isoformat() if row[5] else None
            })
    except SQLAlchemyError as e:
        # Table might not exist or different schema
        logger.debug(f"Could not query audit_logs: {e}")

    return events


def _get_failed_login_stats(app, db) -> Dict[str, Any]:
    """Get failed login attempt statistics."""
    stats = {
        "recent_failed_attempts": 0,
        "unique_ips": 0,
        "top_offenders": []
    }

    try:
        # Try to get from middleware
        for middleware in getattr(app, 'middleware_stack', []):
            if hasattr(middleware, 'app') and hasattr(middleware.app, 'failed_attempts'):
                attempts = middleware.app.failed_attempts
                stats["unique_ips"] = len(attempts)
                stats["recent_failed_attempts"] = sum(len(v) for v in attempts.values())

                # Top offenders
                top = sorted(
                    [(k, len(v)) for k, v in attempts.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
                stats["top_offenders"] = [{"ip": ip, "attempts": count} for ip, count in top]
                break
    except Exception as e:
        logger.debug(f"Could not get failed login stats: {e}")

    return stats
