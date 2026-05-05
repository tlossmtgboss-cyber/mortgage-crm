"""
Billing Admin Routes — LIC-004, LIC-006, LIC-011, LIC-012

Endpoints:
    POST /api/v1/admin/billing/check-feature        — Feature gating check (LIC-004)
    POST /api/v1/admin/billing/track-usage           — Usage metering hook (LIC-006)
    POST /api/v1/admin/billing/prorate-change        — Proration calculation (LIC-011)
    GET  /api/v1/admin/billing/subscription           — View org subscription (LIC-012)
    POST /api/v1/admin/billing/change-plan            — Change subscription plan (LIC-012)
    GET  /api/v1/admin/billing/invoices               — List invoices (LIC-012)
    POST /api/v1/admin/billing/payment-method          — Update payment method (LIC-012)
    GET  /api/v1/admin/billing/usage-summary           — Usage breakdown (LIC-012)
"""
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)


class FeatureCheckRequest(BaseModel):
    feature_key: str


class UsageTrackRequest(BaseModel):
    feature_key: str
    amount: int = 1


class PlanChangeRequest(BaseModel):
    new_tier: str
    billing_cycle: str = "monthly"  # monthly or annual


class PaymentMethodRequest(BaseModel):
    stripe_payment_method_id: str


def register_billing_admin_routes(app, get_db, get_current_user, **kwargs):
    """Register billing admin endpoints (LIC-004, LIC-006, LIC-011, LIC-012)."""

    # ==================================================================
    # LIC-004: Feature gating by tier — integrated endpoint
    # ==================================================================
    @app.post("/api/v1/admin/billing/check-feature", tags=["Billing"])
    async def check_feature_access(
        body: FeatureCheckRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Check if the current organization can access a feature.
        Uses @require_feature() / @require_tier() decorator infrastructure
        and SubscriptionService.can_access_feature() underneath.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=400, detail="No organization")

        from subscription_service import SubscriptionService
        result = SubscriptionService.can_access_feature(db, org_id, body.feature_key)
        return {"feature_key": body.feature_key, **result}

    # ==================================================================
    # LIC-006: Usage-based billing hooks — auto-metering endpoint
    # ==================================================================
    @app.post("/api/v1/admin/billing/track-usage", tags=["Billing"])
    async def track_feature_usage(
        body: UsageTrackRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Auto-metering hook: increment usage for a billable feature.
        Called by business logic (lead creation, AI queries, document uploads)
        to track consumption against subscription limits.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=400, detail="No organization")

        from subscription_service import SubscriptionService
        result = SubscriptionService.increment_usage(db, org_id, body.feature_key, body.amount)

        # Check for overage warnings after increment
        warnings = SubscriptionService.check_usage_warnings(db, org_id)
        return {
            "feature_key": body.feature_key,
            "amount": body.amount,
            **result,
            "warnings": warnings,
        }

    # ==================================================================
    # LIC-011: Proration on plan changes
    # ==================================================================
    @app.post("/api/v1/admin/billing/prorate-change", tags=["Billing"])
    async def prorate_plan_change(
        body: PlanChangeRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Calculate and apply prorated billing when changing subscription tiers.

        Proration logic:
        1. Calculate days remaining in current period
        2. Credit unused portion of current plan
        3. Charge prorated amount for new plan
        4. Return net adjustment (credit or charge)
        """
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=400, detail="No organization")

        try:
            # Get current subscription
            row = db.execute(text("""
                SELECT tier, monthly_price, current_period_start, current_period_end,
                       billing_cycle, stripe_subscription_id
                FROM organization_subscriptions
                WHERE organization_id = :org_id AND status = 'active'
                LIMIT 1
            """), {"org_id": org_id}).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="No active subscription")

            old_tier = row[0]
            old_price = float(row[1] or 0)
            period_start = row[2]
            period_end = row[3]
            billing_cycle = row[4] or "monthly"
            stripe_sub_id = row[5]

            # Get new tier pricing
            from subscription_models import SUBSCRIPTION_TIERS
            new_config = SUBSCRIPTION_TIERS.get(body.new_tier)
            if not new_config:
                raise HTTPException(status_code=400, detail=f"Invalid tier: {body.new_tier}")

            new_price = new_config.get("price_monthly", 0)
            if body.billing_cycle == "annual":
                new_price = new_config.get("price_annual", new_price * 12) / 12

            # Calculate proration
            now = datetime.now(timezone.utc)
            if period_start and period_end:
                total_days = (period_end - period_start).days or 30
                days_used = (now - period_start).days
                days_remaining = max(total_days - days_used, 0)
            else:
                total_days = 30
                days_remaining = 15  # Default assumption

            # Credit for unused portion of old plan
            daily_old = old_price / total_days
            credit = round(daily_old * days_remaining, 2)

            # Charge for prorated new plan
            daily_new = new_price / total_days
            charge = round(daily_new * days_remaining, 2)

            # Net adjustment
            net_adjustment = round(charge - credit, 2)

            # Apply the tier change
            db.execute(text("""
                UPDATE organization_subscriptions
                SET tier = :new_tier,
                    monthly_price = :new_price,
                    billing_cycle = :cycle,
                    proration_credit = :credit,
                    updated_at = NOW()
                WHERE organization_id = :org_id
            """), {
                "new_tier": body.new_tier,
                "new_price": new_price,
                "cycle": body.billing_cycle,
                "credit": credit,
                "org_id": org_id,
            })

            # Log the proration event
            db.execute(text("""
                INSERT INTO audit_logs
                    (user_id, changed_by_id, change_type, entity_type, reason,
                     before_state, after_state, timestamp, organization_id)
                VALUES
                    (:user_id, :user_id, 'plan_change', 'subscription', 'proration',
                     CAST(:before AS jsonb), CAST(:after AS jsonb), NOW(), :org_id)
            """), {
                "user_id": current_user.id,
                "org_id": org_id,
                "before": json.dumps({"tier": old_tier, "price": old_price}),
                "after": json.dumps({
                    "tier": body.new_tier, "price": new_price,
                    "credit": credit, "charge": charge, "net": net_adjustment,
                }),
            })
            db.commit()

            return {
                "status": "applied",
                "old_tier": old_tier,
                "new_tier": body.new_tier,
                "proration": {
                    "days_remaining": days_remaining,
                    "total_days": total_days,
                    "old_daily_rate": daily_old,
                    "new_daily_rate": daily_new,
                    "credit_amount": credit,
                    "charge_amount": charge,
                    "net_adjustment": net_adjustment,
                },
                "new_monthly_price": new_price,
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Proration failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Plan change failed")

    # ==================================================================
    # LIC-012: Billing admin portal — subscription management
    # ==================================================================
    @app.get("/api/v1/admin/billing/subscription", tags=["Billing"])
    async def get_org_subscription(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get full subscription details for the current organization."""
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=400, detail="No organization")

        from subscription_service import SubscriptionService
        sub = SubscriptionService.get_organization_subscription(db, org_id)
        if not sub:
            return {"subscription": None, "message": "No subscription found"}

        # Get tier features
        features = SubscriptionService.get_tier_features(sub["tier"])
        usage = SubscriptionService.get_usage_summary(db, org_id)

        return {
            "subscription": sub,
            "features": features,
            "usage": usage,
        }

    @app.post("/api/v1/admin/billing/change-plan", tags=["Billing"])
    async def change_subscription_plan(
        body: PlanChangeRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Change subscription plan with proration (wraps prorate-change)."""
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)
        from subscription_service import SubscriptionService
        result = SubscriptionService.upgrade_tier(db, org_id, body.new_tier, current_user.id)
        return result

    @app.get("/api/v1/admin/billing/invoices", tags=["Billing"])
    async def list_invoices(
        limit: int = 20,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List invoices for the current organization."""
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)

        try:
            rows = db.execute(text("""
                SELECT id, invoice_number, status, total_amount, currency,
                       period_start, period_end, due_date, paid_at, created_at,
                       line_items, pdf_url
                FROM invoices
                WHERE organization_id = :org_id
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"org_id": org_id, "limit": limit}).fetchall()

            invoices = []
            for r in rows:
                invoices.append({
                    "id": r[0],
                    "invoice_number": r[1],
                    "status": r[2],
                    "total_amount": float(r[3]) if r[3] else 0,
                    "currency": r[4] or "usd",
                    "period_start": str(r[5]) if r[5] else None,
                    "period_end": str(r[6]) if r[6] else None,
                    "due_date": str(r[7]) if r[7] else None,
                    "paid_at": str(r[8]) if r[8] else None,
                    "created_at": str(r[9]) if r[9] else None,
                    "pdf_url": r[11],
                })

            return {"invoices": invoices, "total": len(invoices)}
        except Exception as e:
            logger.warning(f"Invoice listing: {e}")
            return {"invoices": [], "total": 0, "note": "Invoice table may not exist yet"}

    @app.post("/api/v1/admin/billing/payment-method", tags=["Billing"])
    async def update_payment_method(
        body: PaymentMethodRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update payment method for the organization (Stripe integration)."""
        from utils.auth import require_admin
        require_admin(current_user)

        org_id = getattr(current_user, 'organization_id', None)

        try:
            db.execute(text("""
                UPDATE organization_subscriptions
                SET stripe_payment_method_id = :pm_id, updated_at = NOW()
                WHERE organization_id = :org_id
            """), {"pm_id": body.stripe_payment_method_id, "org_id": org_id})
            db.commit()
            return {"status": "updated", "payment_method_id": body.stripe_payment_method_id}
        except Exception as e:
            db.rollback()
            logger.error(f"Payment method update failed: {e}")
            raise HTTPException(status_code=500, detail="Payment method update failed")

    @app.get("/api/v1/admin/billing/usage-summary", tags=["Billing"])
    async def get_usage_summary(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get detailed usage breakdown for the current billing period."""
        org_id = getattr(current_user, 'organization_id', None)

        from subscription_service import SubscriptionService
        usage = SubscriptionService.get_usage_summary(db, org_id)
        warnings = SubscriptionService.check_usage_warnings(db, org_id)

        return {
            "organization_id": org_id,
            "usage": usage,
            "warnings": warnings,
        }

    logger.info("Billing admin routes loaded (LIC-004/006/011/012)")
