"""
Subscription & Permission Service
Handles tier validation, feature access, and usage tracking
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import logging
import json

from subscription_models import SUBSCRIPTION_TIERS, FEATURE_ADDONS

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Handles subscription tier checks and permissions"""

    # Tier hierarchy (higher index = more access)
    TIER_HIERARCHY = ['lead_management', 'lead_and_active', 'full_pipeline']

    @staticmethod
    def get_organization_subscription(db: Session, organization_id: int) -> Optional[Dict]:
        """Get subscription details for an organization"""
        try:
            result = db.execute(text("""
                SELECT id, tier, status, billing_cycle, monthly_price,
                       trial_ends_at, current_period_end, enabled_addons
                FROM organization_subscriptions
                WHERE organization_id = :org_id
            """), {"org_id": organization_id})

            row = result.fetchone()
            if not row:
                return None

            return {
                "id": str(row[0]),
                "tier": row[1],
                "status": row[2],
                "billing_cycle": row[3],
                "monthly_price": float(row[4]) if row[4] else 0,
                "trial_ends_at": row[5].isoformat() if row[5] else None,
                "current_period_end": row[6].isoformat() if row[6] else None,
                "enabled_addons": row[7] or []
            }
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None

    @staticmethod
    def has_tier_access(current_tier: str, required_tier: str) -> bool:
        """Check if current tier has access to features requiring required_tier"""
        hierarchy = SubscriptionService.TIER_HIERARCHY

        if current_tier not in hierarchy or required_tier not in hierarchy:
            return False

        return hierarchy.index(current_tier) >= hierarchy.index(required_tier)

    @staticmethod
    def can_access_feature(db: Session, organization_id: int, feature_key: str) -> Dict[str, Any]:
        """Check if organization can access a feature"""
        try:
            # Get subscription
            sub = SubscriptionService.get_organization_subscription(db, organization_id)
            if not sub:
                return {
                    "allowed": False,
                    "reason": "no_subscription",
                    "message": "No active subscription found"
                }

            # Check subscription status
            if sub["status"] not in ["active", "trial"]:
                return {
                    "allowed": False,
                    "reason": "inactive_subscription",
                    "message": f"Subscription is {sub['status']}"
                }

            # Get feature definition
            result = db.execute(text("""
                SELECT min_tier, monthly_limit, is_addon
                FROM feature_definitions
                WHERE feature_key = :key AND is_active = TRUE
            """), {"key": feature_key})

            feature = result.fetchone()
            if not feature:
                # Unknown feature - allow by default
                return {"allowed": True, "reason": "unknown_feature"}

            min_tier, monthly_limit, is_addon = feature

            # Check if addon required
            if is_addon and feature_key not in sub.get("enabled_addons", []):
                return {
                    "allowed": False,
                    "reason": "addon_required",
                    "message": f"Feature requires {feature_key} addon"
                }

            # Check tier access
            if not SubscriptionService.has_tier_access(sub["tier"], min_tier):
                tier_name = SUBSCRIPTION_TIERS.get(min_tier, {}).get("name", min_tier)
                return {
                    "allowed": False,
                    "reason": "tier_required",
                    "message": f"Feature requires {tier_name} tier or higher",
                    "required_tier": min_tier
                }

            # Check usage limits if applicable
            if monthly_limit:
                usage = SubscriptionService.get_current_usage(db, organization_id, feature_key)
                if usage >= monthly_limit:
                    return {
                        "allowed": False,
                        "reason": "limit_reached",
                        "message": f"Monthly limit of {monthly_limit} reached",
                        "usage": usage,
                        "limit": monthly_limit
                    }

                return {
                    "allowed": True,
                    "usage": usage,
                    "limit": monthly_limit,
                    "remaining": monthly_limit - usage
                }

            return {"allowed": True}

        except Exception as e:
            logger.error(f"Error checking feature access: {e}")
            return {"allowed": False, "reason": "error", "message": "Internal server error"}

    @staticmethod
    def get_current_usage(db: Session, organization_id: int, feature_key: str) -> int:
        """Get current period usage for a feature"""
        try:
            now = datetime.now(timezone.utc)
            result = db.execute(text("""
                SELECT COALESCE(usage_count, 0)
                FROM feature_usage
                WHERE organization_id = :org_id
                AND feature_key = :key
                AND period_start <= :now AND period_end > :now
            """), {"org_id": organization_id, "key": feature_key, "now": now})

            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting usage: {e}")
            return 0

    @staticmethod
    def increment_usage(db: Session, organization_id: int, feature_key: str, amount: int = 1) -> Dict[str, Any]:
        """Increment usage counter for a feature"""
        try:
            now = datetime.now(timezone.utc)

            # Get or create current period
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                period_end = period_start.replace(year=now.year + 1, month=1)
            else:
                period_end = period_start.replace(month=now.month + 1)

            # Try to update existing record
            result = db.execute(text("""
                UPDATE feature_usage
                SET usage_count = usage_count + :amount,
                    updated_at = NOW()
                WHERE organization_id = :org_id
                AND feature_key = :key
                AND period_start = :period_start
                RETURNING usage_count
            """), {
                "org_id": organization_id,
                "key": feature_key,
                "amount": amount,
                "period_start": period_start
            })

            row = result.fetchone()
            if row:
                db.commit()
                return {"success": True, "new_count": row[0]}

            # Create new record
            db.execute(text("""
                INSERT INTO feature_usage
                (organization_id, feature_key, usage_count, period_start, period_end)
                VALUES (:org_id, :key, :amount, :period_start, :period_end)
            """), {
                "org_id": organization_id,
                "key": feature_key,
                "amount": amount,
                "period_start": period_start,
                "period_end": period_end
            })
            db.commit()

            return {"success": True, "new_count": amount}

        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
            db.rollback()
            return {"success": False, "error": "Internal server error"}

    @staticmethod
    def get_usage_summary(db: Session, organization_id: int) -> Dict[str, Any]:
        """Get complete usage summary for organization"""
        try:
            now = datetime.now(timezone.utc)

            # Get all usage for current period
            result = db.execute(text("""
                SELECT fu.feature_key, fu.usage_count, fd.monthly_limit, fd.name
                FROM feature_usage fu
                JOIN feature_definitions fd ON fu.feature_key = fd.feature_key
                WHERE fu.organization_id = :org_id
                AND fu.period_start <= :now AND fu.period_end > :now
            """), {"org_id": organization_id, "now": now})

            usage = {}
            for row in result:
                key, count, limit, name = row
                usage[key] = {
                    "name": name,
                    "used": count,
                    "limit": limit,
                    "remaining": limit - count if limit else None,
                    "percent": round((count / limit) * 100, 1) if limit else None
                }

            return usage

        except Exception as e:
            logger.error(f"Error getting usage summary: {e}")
            return {}

    @staticmethod
    def check_usage_warnings(db: Session, organization_id: int) -> List[Dict]:
        """Check and create usage warnings at 80%, 90%, 100%"""
        warnings = []
        try:
            usage = SubscriptionService.get_usage_summary(db, organization_id)

            for key, data in usage.items():
                if data["percent"] is None:
                    continue

                # Check thresholds
                for threshold in [80, 90, 100]:
                    if data["percent"] >= threshold:
                        # Check if warning already sent
                        result = db.execute(text("""
                            SELECT id FROM usage_warnings
                            WHERE organization_id = :org_id
                            AND feature_key = :key
                            AND threshold_percent = :threshold
                            AND created_at > NOW() - INTERVAL '30 days'
                        """), {"org_id": organization_id, "key": key, "threshold": threshold})

                        if not result.fetchone():
                            # Create warning
                            warning_type = "limit_reached" if threshold == 100 else "approaching_limit"
                            message = f"{data['name']}: {data['used']}/{data['limit']} used ({data['percent']}%)"

                            db.execute(text("""
                                INSERT INTO usage_warnings
                                (organization_id, feature_key, warning_type, threshold_percent, message)
                                VALUES (:org_id, :key, :type, :threshold, :message)
                            """), {
                                "org_id": organization_id,
                                "key": key,
                                "type": warning_type,
                                "threshold": threshold,
                                "message": message
                            })

                            warnings.append({
                                "feature": key,
                                "type": warning_type,
                                "threshold": threshold,
                                "message": message
                            })

            if warnings:
                db.commit()

            return warnings

        except Exception as e:
            logger.error(f"Error checking warnings: {e}")
            db.rollback()
            return []

    @staticmethod
    def get_tier_features(tier: str) -> Dict[str, Any]:
        """Get all features available for a tier"""
        tier_config = SUBSCRIPTION_TIERS.get(tier)
        if not tier_config:
            return {}

        return {
            "name": tier_config["name"],
            "price_monthly": tier_config["price_monthly"],
            "price_annual": tier_config["price_annual"],
            "stages": tier_config["stages"],
            "features": tier_config["features"]
        }

    @staticmethod
    def get_allowed_stages(db: Session, organization_id: int) -> List[str]:
        """Get list of pipeline stages allowed for organization's tier"""
        sub = SubscriptionService.get_organization_subscription(db, organization_id)
        if not sub:
            return []

        tier_config = SUBSCRIPTION_TIERS.get(sub["tier"])
        if not tier_config:
            return []

        stages = tier_config.get("stages", [])
        if stages == "all":
            # Return all stages
            return [
                'lead_received', 'contacted', 'qualified', 'pre_approved', 'application',
                'ratified_contract', 'processing', 'underwriting', 'conditional_approval',
                'clear_to_close', 'closing', 'funding', 'post_close', 'servicing'
            ]

        return stages

    @staticmethod
    def upgrade_tier(db: Session, organization_id: int, new_tier: str, admin_user_id: int = None) -> Dict[str, Any]:
        """Upgrade organization to a new tier"""
        try:
            # Get current subscription
            result = db.execute(text("""
                SELECT tier, monthly_price FROM organization_subscriptions
                WHERE organization_id = :org_id
            """), {"org_id": organization_id})

            current = result.fetchone()
            if not current:
                return {"success": False, "error": "No subscription found"}

            old_tier, old_price = current

            # Get new tier pricing
            new_config = SUBSCRIPTION_TIERS.get(new_tier)
            if not new_config:
                return {"success": False, "error": "Invalid tier"}

            new_price = new_config["price_monthly"]

            # Update subscription
            db.execute(text("""
                UPDATE organization_subscriptions
                SET tier = :new_tier,
                    monthly_price = :new_price,
                    updated_at = NOW()
                WHERE organization_id = :org_id
            """), {
                "org_id": organization_id,
                "new_tier": new_tier,
                "new_price": new_price
            })

            # Log admin action
            if admin_user_id:
                db.execute(text("""
                    INSERT INTO admin_actions
                    (admin_user_id, organization_id, action_type, description, previous_value, new_value)
                    VALUES (:admin_id, :org_id, 'tier_upgrade', :desc,
                            CAST(:prev AS jsonb), CAST(:new AS jsonb))
                """), {
                    "admin_id": admin_user_id,
                    "org_id": organization_id,
                    "desc": f"Upgraded from {old_tier} to {new_tier}",
                    "prev": json.dumps({"tier": old_tier, "price": float(old_price)}),
                    "new": json.dumps({"tier": new_tier, "price": new_price})
                })

            db.commit()

            return {
                "success": True,
                "old_tier": old_tier,
                "new_tier": new_tier,
                "new_price": new_price
            }

        except Exception as e:
            logger.error(f"Error upgrading tier: {e}")
            db.rollback()
            return {"success": False, "error": "Internal server error"}


class PermissionChecker:
    """Decorator and utilities for checking permissions"""

    @staticmethod
    def require_feature(feature_key: str):
        """Decorator to require a feature for an endpoint"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Get db and organization_id from kwargs
                db = kwargs.get('db')
                organization_id = kwargs.get('organization_id')

                if db and organization_id:
                    access = SubscriptionService.can_access_feature(db, organization_id, feature_key)
                    if not access.get("allowed"):
                        from fastapi import HTTPException
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "feature_not_available",
                                "reason": access.get("reason"),
                                "message": access.get("message")
                            }
                        )

                    # Track usage if applicable
                    SubscriptionService.increment_usage(db, organization_id, feature_key)

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    def require_tier(min_tier: str):
        """Decorator to require minimum tier"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                db = kwargs.get('db')
                organization_id = kwargs.get('organization_id')

                if db and organization_id:
                    sub = SubscriptionService.get_organization_subscription(db, organization_id)
                    if not sub:
                        from fastapi import HTTPException
                        raise HTTPException(status_code=403, detail="No subscription")

                    if not SubscriptionService.has_tier_access(sub["tier"], min_tier):
                        from fastapi import HTTPException
                        raise HTTPException(
                            status_code=403,
                            detail=f"Requires {min_tier} tier or higher"
                        )

                return await func(*args, **kwargs)
            return wrapper
        return decorator
