"""
Subscription Enforcement Middleware (LIC-006)

Blocks API access after grace period expires for PAST_DUE subscriptions.
Returns 402 Payment Required when the organization's subscription grace period
has expired, while allowing access to billing, auth, and health endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Paths that are always allowed even after grace period expiration
EXEMPT_PATH_PREFIXES = (
    "/webhooks/",           # Stripe and other webhooks must always work
    "/api/v1/billing",      # Must be able to view/update billing
    "/api/v1/subscription", # Must be able to manage subscription
    "/api/v1/auth",         # Must be able to log in/out
    "/api/v1/payment",      # Must be able to add payment methods
    "/health",              # Health checks
    "/docs",                # API docs
    "/openapi",             # OpenAPI schema
    "/redoc",               # Redoc docs
)


class SubscriptionEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that blocks API access when subscription grace period has expired.

    After a payment failure, a 14-day grace period is granted. Once expired,
    the organization receives 402 Payment Required on all non-billing endpoints
    until payment is resolved.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip non-API paths and exempt paths
        path = request.url.path
        if not path.startswith("/api/") or any(path.startswith(p) for p in EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        # Skip if no organization context (unauthenticated requests handled elsewhere)
        org_id = getattr(request.state, 'organization_id', None)
        if not org_id:
            return await call_next(request)

        # Check subscription status
        try:
            grace_expired = self._check_grace_period_expired(request, org_id)
            if grace_expired:
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": "Payment Required",
                        "message": "Your subscription payment is overdue and the grace period has expired. Please update your payment method to restore access.",
                        "code": "GRACE_PERIOD_EXPIRED",
                    },
                )
        except Exception as e:
            # Don't block on middleware errors — log and allow through
            logger.error(f"Subscription enforcement check failed: {e}")

        return await call_next(request)

    def _check_grace_period_expired(self, request: Request, org_id: int) -> bool:
        """Check if the organization's subscription grace period has expired."""
        # Import here to avoid circular imports at module load time
        from models.billing import Subscription, SubscriptionStatus

        db: Optional[Session] = getattr(request.state, 'db', None)
        if not db:
            return False

        try:
            subscription = db.execute(
                select(Subscription).where(
                    Subscription.organization_id == org_id,
                    Subscription.status == SubscriptionStatus.PAST_DUE,
                    Subscription.grace_period_ends_at.isnot(None),
                )
            ).scalar_one_or_none()

            if not subscription:
                return False

            now = datetime.now(timezone.utc)
            return subscription.grace_period_ends_at < now
        except Exception:
            return False
