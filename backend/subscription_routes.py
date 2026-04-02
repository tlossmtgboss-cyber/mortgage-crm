"""
Subscription API Routes
Admin and user endpoints for subscription management
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel
import json
import logging

from database import get_db
from routes.auth_deps import require_auth
from subscription_service import SubscriptionService
from subscription_models import SUBSCRIPTION_TIERS, FEATURE_ADDONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"], dependencies=[Depends(require_auth)])


# === Pydantic Models ===

class SubscriptionCreate(BaseModel):
    organization_id: int
    tier: str = "lead_management"
    billing_cycle: str = "monthly"


class TierUpgrade(BaseModel):
    new_tier: str


class AddonToggle(BaseModel):
    addon_key: str
    enabled: bool


class UsageResponse(BaseModel):
    feature_key: str
    name: str
    used: int
    limit: Optional[int]
    remaining: Optional[int]
    percent: Optional[float]


# === Public Endpoints ===

@router.get("/tiers")
async def get_subscription_tiers():
    """Get all available subscription tiers and pricing"""
    tiers = []
    for key, config in SUBSCRIPTION_TIERS.items():
        tiers.append({
            "key": key,
            "name": config["name"],
            "price_monthly": config["price_monthly"],
            "price_annual": config["price_annual"],
            "stages": config["stages"],
            "features": config["features"]
        })
    return {"tiers": tiers}


@router.get("/addons")
async def get_available_addons():
    """Get all available feature addons"""
    addons = []
    for key, config in FEATURE_ADDONS.items():
        addons.append({
            "key": key,
            "price": config["price"],
            "amount": config["amount"],
            "unit": config["unit"]
        })
    return {"addons": addons}


# === User Endpoints (requires authentication) ===

@router.get("/my-subscription")
async def get_my_subscription(
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Get current user's organization subscription"""
    sub = SubscriptionService.get_organization_subscription(db, organization_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")

    # Add tier details
    tier_details = SubscriptionService.get_tier_features(sub["tier"])

    return {
        "subscription": sub,
        "tier_details": tier_details
    }


@router.get("/my-usage")
async def get_my_usage(
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Get usage summary for current period"""
    usage = SubscriptionService.get_usage_summary(db, organization_id)
    return {"usage": usage}


@router.get("/my-allowed-stages")
async def get_my_allowed_stages(
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Get pipeline stages allowed for current tier"""
    stages = SubscriptionService.get_allowed_stages(db, organization_id)
    return {"stages": stages}


@router.post("/check-feature/{feature_key}")
async def check_feature_access(
    feature_key: str,
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Check if organization can access a specific feature"""
    access = SubscriptionService.can_access_feature(db, organization_id, feature_key)
    return access


@router.get("/my-warnings")
async def get_my_warnings(
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Get unacknowledged usage warnings"""
    try:
        result = db.execute(text("""
            SELECT id, feature_key, warning_type, threshold_percent, message, created_at
            FROM usage_warnings
            WHERE organization_id = :org_id AND acknowledged = FALSE
            ORDER BY created_at DESC
        """), {"org_id": organization_id})

        warnings = []
        for row in result:
            warnings.append({
                "id": str(row[0]),
                "feature_key": row[1],
                "warning_type": row[2],
                "threshold_percent": row[3],
                "message": row[4],
                "created_at": row[5].isoformat() if row[5] else None
            })

        return {"warnings": warnings}
    except Exception as e:
        logger.error(f"Error getting warnings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/acknowledge-warning/{warning_id}")
async def acknowledge_warning(
    warning_id: str,
    user_id: int,
    db: Session = Depends(get_db)
):
    """Acknowledge a usage warning"""
    try:
        db.execute(text("""
            UPDATE usage_warnings
            SET acknowledged = TRUE, acknowledged_at = NOW(), acknowledged_by = :user_id
            WHERE id = CAST(:warning_id AS uuid)
        """), {"warning_id": warning_id, "user_id": user_id})
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# === Admin Endpoints ===

@router.get("/admin/list")
async def admin_list_subscriptions(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    tier: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Admin: List all organization subscriptions"""
    try:
        query = """
            SELECT os.id, os.organization_id, os.tier, os.status, os.billing_cycle,
                   os.monthly_price, os.current_period_end, os.created_at
            FROM organization_subscriptions os
            WHERE 1=1
        """
        params = {}

        if status:
            query += " AND os.status = :status"
            params["status"] = status

        if tier:
            query += " AND os.tier = :tier"
            params["tier"] = tier

        query += " ORDER BY os.created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = db.execute(text(query), params)

        subscriptions = []
        for row in result:
            subscriptions.append({
                "id": str(row[0]),
                "organization_id": row[1],
                "tier": row[2],
                "status": row[3],
                "billing_cycle": row[4],
                "monthly_price": float(row[5]) if row[5] else 0,
                "current_period_end": row[6].isoformat() if row[6] else None,
                "created_at": row[7].isoformat() if row[7] else None
            })

        # Get total count
        count_result = db.execute(text("""
            SELECT COUNT(*) FROM organization_subscriptions
        """))
        total = count_result.scalar()

        return {
            "subscriptions": subscriptions,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing subscriptions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/create")
async def admin_create_subscription(
    data: SubscriptionCreate,
    admin_user_id: int,
    db: Session = Depends(get_db)
):
    """Admin: Create subscription for an organization"""
    try:
        # Check if already exists
        result = db.execute(text("""
            SELECT id FROM organization_subscriptions WHERE organization_id = :org_id
        """), {"org_id": data.organization_id})

        if result.fetchone():
            raise HTTPException(status_code=400, detail="Subscription already exists")

        # Get pricing
        tier_config = SUBSCRIPTION_TIERS.get(data.tier)
        if not tier_config:
            raise HTTPException(status_code=400, detail="Invalid tier")

        price = tier_config["price_monthly"] if data.billing_cycle == "monthly" else tier_config["price_annual"] / 12

        # Create subscription
        now = datetime.now(timezone.utc)
        period_end = now.replace(day=1)
        if now.month == 12:
            period_end = period_end.replace(year=now.year + 1, month=1)
        else:
            period_end = period_end.replace(month=now.month + 1)

        db.execute(text("""
            INSERT INTO organization_subscriptions
            (organization_id, tier, billing_cycle, monthly_price, status,
             current_period_start, current_period_end)
            VALUES (:org_id, :tier, :cycle, :price, 'active', :start, :end)
        """), {
            "org_id": data.organization_id,
            "tier": data.tier,
            "cycle": data.billing_cycle,
            "price": price,
            "start": now,
            "end": period_end
        })

        # Log admin action
        db.execute(text("""
            INSERT INTO admin_actions
            (admin_user_id, organization_id, action_type, description, new_value)
            VALUES (:admin_id, :org_id, 'subscription_created', :desc, CAST(:value AS jsonb))
        """), {
            "admin_id": admin_user_id,
            "org_id": data.organization_id,
            "desc": f"Created {data.tier} subscription",
            "value": json.dumps({"tier": data.tier, "price": price})
        })

        db.commit()

        return {"success": True, "tier": data.tier, "price": price}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/upgrade/{organization_id}")
async def admin_upgrade_tier(
    organization_id: int,
    data: TierUpgrade,
    admin_user_id: int,
    db: Session = Depends(get_db)
):
    """Admin: Upgrade organization tier"""
    result = SubscriptionService.upgrade_tier(db, organization_id, data.new_tier, admin_user_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/admin/set-status/{organization_id}")
async def admin_set_subscription_status(
    organization_id: int,
    status: str,
    admin_user_id: int,
    db: Session = Depends(get_db)
):
    """Admin: Set subscription status (active, trial, past_due, canceled)"""
    try:
        valid_statuses = ["active", "trial", "past_due", "canceled"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

        # Get current status
        result = db.execute(text("""
            SELECT status FROM organization_subscriptions WHERE organization_id = :org_id
        """), {"org_id": organization_id})

        current = result.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Subscription not found")

        old_status = current[0]

        # Update status
        db.execute(text("""
            UPDATE organization_subscriptions
            SET status = :status, updated_at = NOW()
            WHERE organization_id = :org_id
        """), {"org_id": organization_id, "status": status})

        # Log admin action
        db.execute(text("""
            INSERT INTO admin_actions
            (admin_user_id, organization_id, action_type, description, previous_value, new_value)
            VALUES (:admin_id, :org_id, 'status_change', :desc, CAST(:prev AS jsonb), CAST(:new AS jsonb))
        """), {
            "admin_id": admin_user_id,
            "org_id": organization_id,
            "desc": f"Changed status from {old_status} to {status}",
            "prev": json.dumps({"status": old_status}),
            "new": json.dumps({"status": status})
        })

        db.commit()
        return {"success": True, "old_status": old_status, "new_status": status}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/toggle-addon/{organization_id}")
async def admin_toggle_addon(
    organization_id: int,
    data: AddonToggle,
    admin_user_id: int,
    db: Session = Depends(get_db)
):
    """Admin: Enable or disable an addon for organization"""
    try:
        # Get current addons
        result = db.execute(text("""
            SELECT enabled_addons FROM organization_subscriptions WHERE organization_id = :org_id
        """), {"org_id": organization_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscription not found")

        current_addons = row[0] or []

        # Update addons list
        if data.enabled:
            if data.addon_key not in current_addons:
                current_addons.append(data.addon_key)
        else:
            if data.addon_key in current_addons:
                current_addons.remove(data.addon_key)

        # Save
        db.execute(text("""
            UPDATE organization_subscriptions
            SET enabled_addons = CAST(:addons AS jsonb), updated_at = NOW()
            WHERE organization_id = :org_id
        """), {"org_id": organization_id, "addons": json.dumps(current_addons)})

        # Log action
        action = "enabled" if data.enabled else "disabled"
        db.execute(text("""
            INSERT INTO admin_actions
            (admin_user_id, organization_id, action_type, description)
            VALUES (:admin_id, :org_id, 'addon_toggle', :desc)
        """), {
            "admin_id": admin_user_id,
            "org_id": organization_id,
            "desc": f"{action} addon: {data.addon_key}"
        })

        db.commit()
        return {"success": True, "enabled_addons": current_addons}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/usage/{organization_id}")
async def admin_get_organization_usage(
    organization_id: int,
    db: Session = Depends(get_db)
):
    """Admin: Get detailed usage for an organization"""
    usage = SubscriptionService.get_usage_summary(db, organization_id)

    # Check for warnings
    warnings = SubscriptionService.check_usage_warnings(db, organization_id)

    return {
        "organization_id": organization_id,
        "usage": usage,
        "new_warnings": warnings
    }


@router.get("/admin/actions")
async def admin_get_action_log(
    organization_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Admin: Get audit log of admin actions"""
    try:
        query = """
            SELECT aa.id, aa.admin_user_id, aa.organization_id, aa.action_type,
                   aa.description, aa.created_at, u.email as admin_email
            FROM admin_actions aa
            LEFT JOIN users u ON aa.admin_user_id = u.id
        """
        params = {}

        if organization_id:
            query += " WHERE aa.organization_id = :org_id"
            params["org_id"] = organization_id

        query += " ORDER BY aa.created_at DESC LIMIT :limit"
        params["limit"] = limit

        result = db.execute(text(query), params)

        actions = []
        for row in result:
            actions.append({
                "id": str(row[0]),
                "admin_user_id": row[1],
                "organization_id": row[2],
                "action_type": row[3],
                "description": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "admin_email": row[6]
            })

        return {"actions": actions}

    except Exception as e:
        logger.error(f"Error getting action log: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
