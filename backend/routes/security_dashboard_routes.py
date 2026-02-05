"""
Security Dashboard Routes

This module provides admin endpoints for viewing security metrics and managing
blocked IP addresses. These endpoints are restricted to admin and management roles.

Endpoints:
- GET /api/v1/admin/security/dashboard - Get security dashboard metrics
- POST /api/v1/admin/security/unblock-ip/{ip} - Unblock a blocked IP address
"""

import logging
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/admin/security",
    tags=["Security Dashboard"]
)


# ============================================================================
# RUNTIME DEPENDENCY HELPERS
# ============================================================================

def get_current_user_dep():
    """Get current user - imports from main at runtime to avoid circular imports."""
    import main
    return main.get_current_user


def get_security_stats():
    """Get security stats - imports from main at runtime to avoid circular imports."""
    import main
    return main.security_stats


def get_logger():
    """Get main logger - imports from main at runtime to avoid circular imports."""
    import main
    return main.logger


# ============================================================================
# SECURITY DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/dashboard")
async def get_security_dashboard(current_user=Depends(get_current_user_dep())):
    """
    Get security dashboard metrics including blocked IPs, rate limits, and failed logins.
    Requires admin or management role.
    """
    if current_user.role not in ['admin', 'management']:
        raise HTTPException(status_code=403, detail="Admin access required")

    security_stats = get_security_stats()
    return security_stats.get_dashboard_data()


@router.post("/unblock-ip/{ip}")
async def unblock_ip_address(ip: str, current_user=Depends(get_current_user_dep())):
    """
    Unblock a blocked IP address.
    Requires admin or management role.
    """
    if current_user.role not in ['admin', 'management']:
        raise HTTPException(status_code=403, detail="Admin access required")

    security_stats = get_security_stats()
    main_logger = get_logger()

    if security_stats.unblock_ip(ip):
        main_logger.info(f"IP {ip} unblocked by {current_user.email}")
        return {"message": f"IP {ip} has been unblocked", "success": True}
    else:
        return {"message": f"IP {ip} was not blocked", "success": False}
