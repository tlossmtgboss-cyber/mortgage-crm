"""
Feature gate middleware and decorator for tier-based access control.

Provides a lightweight decorator that checks whether the current
organization's subscription permits access to a given module's tier.

Usage:
    from middleware.feature_gate import require_feature_tier

    @require_feature_tier("premium")
    async def my_premium_endpoint(...):
        ...

    # Or applied to a router:
    @router.get("/some-endpoint")
    @require_feature_tier("telephony")
    async def telephony_endpoint(request: Request, ...):
        ...

Notes:
    - Core features are always accessible regardless of subscription.
    - Premium and experimental features check the organization's
      feature_tier attribute on request.state.organization.
    - If no organization context is available (e.g., public endpoints),
      the request is allowed through.
"""

import functools
from fastapi import HTTPException, Request
from feature_tiers import FeatureTier, get_tier


def require_feature_tier(module: str):
    """
    Decorator that checks if the organization has access to the specified module's tier.

    For now, core is always accessible. Premium and experimental check
    against the organization's subscription tier (stored in the org record).
    """
    tier = get_tier(module)

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Core features always accessible
            if tier == FeatureTier.CORE:
                return await func(*args, **kwargs)

            # For premium/experimental, check org subscription
            # Extract request from args/kwargs
            request = kwargs.get('request')
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request and hasattr(request.state, 'organization'):
                org = request.state.organization
                org_tier = getattr(org, 'feature_tier', 'core')

                tier_hierarchy = {
                    FeatureTier.CORE: 0,
                    FeatureTier.PREMIUM: 1,
                    FeatureTier.EXPERIMENTAL: 2,
                }

                org_level = tier_hierarchy.get(FeatureTier(org_tier), 0)
                required_level = tier_hierarchy.get(tier, 0)

                if org_level < required_level:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "feature_tier_required",
                            "message": f"This feature requires the '{tier.value}' tier. Contact sales to upgrade.",
                            "required_tier": tier.value,
                            "current_tier": org_tier,
                            "module": module,
                        }
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
