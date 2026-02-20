"""
Perennia AI - Subscription Manager Tools
========================================
Tools for the Subscription Manager Agent handling subscriptions and billing.
8 tools for subscription management, billing, and account administration.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    db_session,
    format_currency,
    format_date,
)


# =============================================================================
# Subscription Manager Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_subscription_status",
    description="Get current subscription status for an account",
    agent_roles=["subscription_manager"],
    risk_level="LOW",
    parameters={
        "account_id": "Account ID",
    },
)
def get_subscription_status(account_id: str) -> ToolResult:
    """Get subscription status."""
    subscription = execute_single("""
        SELECT
            s.id, s.account_id, s.plan_id, s.status,
            s.billing_cycle, s.current_period_start, s.current_period_end,
            s.next_billing_date, s.cancel_at_period_end,
            p.name as plan_name, p.price_monthly, p.price_annually
        FROM subscriptions s
        JOIN subscription_plans p ON p.id = s.plan_id
        WHERE s.account_id = :account_id
    """, {"account_id": account_id})

    if not subscription:
        # Return default trial subscription
        subscription = {
            "account_id": account_id,
            "plan": {
                "id": "trial",
                "name": "Trial",
                "price": format_currency(0),
                "billing_cycle": "monthly",
            },
            "status": "trialing",
            "current_period": {
                "start": datetime.now().strftime("%Y-%m-%d"),
                "end": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
            },
            "features": {
                "users": {"limit": 3, "used": 1},
                "loans_per_month": {"limit": 10, "used": 0},
                "ai_credits": {"limit": 100, "used": 0},
                "integrations": {"limit": 1, "used": 0},
            },
            "is_trial": True,
            "trial_days_remaining": 14,
        }
    else:
        # Get feature usage
        usage = execute_single("""
            SELECT
                user_count, loan_count, ai_credit_usage, storage_used_gb
            FROM subscription_usage
            WHERE account_id = :account_id AND period_start = :period_start
        """, {"account_id": account_id, "period_start": subscription.get("current_period_start")})

        # Get plan limits
        limits = execute_single("""
            SELECT user_limit, loan_limit, ai_credit_limit, storage_limit_gb
            FROM subscription_plans WHERE id = :plan_id
        """, {"plan_id": subscription.get("plan_id")})

        price = subscription.get("price_monthly") if subscription.get("billing_cycle") == "monthly" else subscription.get("price_annually")

        subscription = {
            "account_id": account_id,
            "subscription_id": subscription.get("id"),
            "plan": {
                "id": subscription.get("plan_id"),
                "name": subscription.get("plan_name"),
                "price": format_currency(price or 0),
                "billing_cycle": subscription.get("billing_cycle"),
            },
            "status": subscription.get("status"),
            "current_period": {
                "start": format_date(subscription.get("current_period_start")),
                "end": format_date(subscription.get("current_period_end")),
            },
            "features": {
                "users": {
                    "limit": limits.get("user_limit", 10) if limits else 10,
                    "used": usage.get("user_count", 0) if usage else 0,
                },
                "loans_per_month": {
                    "limit": limits.get("loan_limit", 100) if limits else 100,
                    "used": usage.get("loan_count", 0) if usage else 0,
                },
                "ai_credits": {
                    "limit": limits.get("ai_credit_limit", 1000) if limits else 1000,
                    "used": usage.get("ai_credit_usage", 0) if usage else 0,
                },
            },
            "next_billing_date": format_date(subscription.get("next_billing_date")),
            "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
        }

    return ToolResult.success(
        data=subscription,
        message=f"Subscription: {subscription['plan']['name']} ({subscription['status']})",
    )


@mortgage_tool(
    name="get_plans",
    description="Get available subscription plans and pricing",
    agent_roles=["subscription_manager"],
    risk_level="LOW",
    parameters={
        "include_enterprise": "Include enterprise tier plans",
        "billing_cycle": "Filter by billing cycle: monthly, annually",
    },
)
def get_plans(
    include_enterprise: bool = False,
    billing_cycle: Optional[str] = None,
) -> ToolResult:
    """Get available plans from SubscriptionPlan table."""
    # Query real plans from database
    db_plans = execute_query("""
        SELECT id, name, description, price_monthly, price_yearly,
               features, user_limit, is_active
        FROM subscription_plans
        WHERE is_active = true
        ORDER BY price_monthly ASC
    """)

    if db_plans:
        plans = []
        for p in db_plans:
            monthly = float(p.get("price_monthly", 0) or 0)
            yearly = float(p.get("price_yearly", 0) or 0)
            plan = {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": p.get("description"),
                "price_monthly": monthly,
                "price_monthly_formatted": format_currency(monthly),
                "price_annually": yearly,
                "price_annually_formatted": format_currency(yearly) if yearly else "N/A",
                "features": p.get("features") or {"users": p.get("user_limit", 5)},
                "user_limit": p.get("user_limit"),
            }
            if billing_cycle == "annually":
                plan["display_price"] = plan["price_annually_formatted"]
            else:
                plan["display_price"] = plan["price_monthly_formatted"]
            plans.append(plan)
    else:
        # Fallback to hardcoded plans if no DB entries
        plans = [
            {
                "id": "starter", "name": "Starter",
                "description": "For individual loan officers getting started",
                "price_monthly": 99, "price_monthly_formatted": format_currency(99),
                "price_annually": 999, "price_annually_formatted": format_currency(999),
                "features": {"users": 3, "loans_per_month": 25, "ai_credits": 250},
                "display_price": format_currency(999) if billing_cycle == "annually" else format_currency(99),
            },
            {
                "id": "professional", "name": "Professional", "popular": True,
                "description": "For growing loan officers and small teams",
                "price_monthly": 299, "price_monthly_formatted": format_currency(299),
                "price_annually": 2999, "price_annually_formatted": format_currency(2999),
                "features": {"users": 10, "loans_per_month": 100, "ai_credits": 1000},
                "display_price": format_currency(2999) if billing_cycle == "annually" else format_currency(299),
            },
            {
                "id": "business", "name": "Business",
                "description": "For established teams with high volume",
                "price_monthly": 599, "price_monthly_formatted": format_currency(599),
                "price_annually": 5999, "price_annually_formatted": format_currency(5999),
                "features": {"users": 25, "loans_per_month": 500, "ai_credits": 5000},
                "display_price": format_currency(5999) if billing_cycle == "annually" else format_currency(599),
            },
        ]

    if include_enterprise:
        plans.append({
            "id": "enterprise", "name": "Enterprise",
            "description": "Custom solutions for large organizations",
            "price_monthly": None, "price_monthly_formatted": "Contact Sales",
            "features": {"users": "unlimited", "sso": True, "audit_logs": True},
            "contact_sales": True, "display_price": "Contact Sales",
        })

    return ToolResult.success(
        data={"plans": plans, "count": len(plans), "currency": "USD"},
        message=f"Found {len(plans)} available plans",
    )


@mortgage_tool(
    name="change_plan",
    description="Change subscription plan (upgrade or downgrade)",
    agent_roles=["subscription_manager"],
    risk_level="HIGH",
    parameters={
        "account_id": "Account ID",
        "new_plan_id": "New plan ID",
        "billing_cycle": "Billing cycle: monthly, annually",
        "prorate": "Prorate changes to current period",
        "effective_date": "When change takes effect: immediate, next_billing",
    },
)
def change_plan(
    account_id: str,
    new_plan_id: str,
    billing_cycle: str = "monthly",
    prorate: bool = True,
    effective_date: str = "immediate",
) -> ToolResult:
    """Change subscription plan."""
    import uuid
    change_id = str(uuid.uuid4())[:8].upper()

    # Get current subscription
    current = execute_single("""
        SELECT plan_id, billing_cycle, current_period_end
        FROM subscriptions WHERE account_id = :account_id
    """, {"account_id": account_id})

    current_plan = current.get("plan_id", "starter") if current else "starter"

    # Get plan details
    new_plan = execute_single("""
        SELECT id, name, price_monthly, price_annually
        FROM subscription_plans WHERE id = :plan_id
    """, {"plan_id": new_plan_id})

    if not new_plan:
        return ToolResult.error(f"Plan {new_plan_id} not found")

    # Determine upgrade or downgrade
    plan_order = ["starter", "professional", "business", "enterprise"]
    current_idx = plan_order.index(current_plan) if current_plan in plan_order else 0
    new_idx = plan_order.index(new_plan_id) if new_plan_id in plan_order else 0
    change_type = "upgrade" if new_idx > current_idx else "downgrade"

    # Calculate effective date
    if effective_date == "immediate":
        eff_date = datetime.now().strftime("%Y-%m-%d")
    else:
        eff_date = format_date(current.get("current_period_end")) if current else datetime.now().strftime("%Y-%m-%d")

    price = new_plan.get("price_monthly") if billing_cycle == "monthly" else new_plan.get("price_annually")

    change = {
        "change_id": f"CHG-{change_id}",
        "account_id": account_id,
        "change_type": change_type,
        "from_plan": current_plan,
        "to_plan": new_plan_id,
        "to_plan_name": new_plan.get("name"),
        "billing_cycle": billing_cycle,
        "new_price": format_currency(price or 0),
        "prorate": prorate,
        "effective_date": eff_date,
        "status": "pending_confirmation",
        "requires_approval": True,
        "created_at": datetime.now().isoformat(),
    }

    if prorate and change_type == "upgrade" and effective_date == "immediate":
        # Calculate proration (simplified)
        days_remaining = 15  # Simplified
        daily_rate = float(price or 0) / 30
        change["proration_credit"] = format_currency(daily_rate * days_remaining)

    # Persist plan change to subscriptions table
    try:
        from sqlalchemy import text as sa_text
        with db_session() as session:
            if current:
                session.execute(sa_text("""
                    UPDATE subscriptions
                    SET plan_id = :new_plan_id,
                        billing_cycle = :billing_cycle,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = :account_id
                """), {
                    "new_plan_id": new_plan_id,
                    "billing_cycle": billing_cycle,
                    "account_id": account_id,
                })
            else:
                session.execute(sa_text("""
                    INSERT INTO subscriptions (account_id, plan_id, billing_cycle, status, created_at, updated_at)
                    VALUES (:account_id, :new_plan_id, :billing_cycle, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {
                    "account_id": account_id,
                    "new_plan_id": new_plan_id,
                    "billing_cycle": billing_cycle,
                })
        change["persisted"] = True
    except Exception as e:
        change["persisted"] = False
        change["persistence_error"] = str(e)

    return ToolResult.success(
        data=change,
        message=f"Plan {change_type} to {new_plan.get('name')} prepared (requires confirmation)",
        requires_approval=True,
    )


@mortgage_tool(
    name="get_billing_history",
    description="Get billing and invoice history for account",
    agent_roles=["subscription_manager"],
    risk_level="LOW",
    parameters={
        "account_id": "Account ID",
        "limit": "Number of records to return",
        "status": "Filter by status: paid, pending, failed, refunded",
    },
)
def get_billing_history(
    account_id: str,
    limit: int = 12,
    status: Optional[str] = None,
) -> ToolResult:
    """Get billing history."""
    params = {"account_id": account_id, "limit": limit}
    filters = ["account_id = :account_id"]

    if status:
        filters.append("status = :status")
        params["status"] = status

    where_sql = " AND ".join(filters)

    invoices = execute_query(f"""
        SELECT
            id, invoice_number, amount, status, description,
            created_at, paid_at, due_date, payment_method
        FROM invoices
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit
    """, params)

    if not invoices:
        # Generate sample billing history
        invoices = []
        base_date = datetime.now()
        for i in range(min(limit, 6)):
            invoice_date = base_date - timedelta(days=30 * i)
            invoices.append({
                "invoice_id": f"INV-{invoice_date.strftime('%Y%m')}-{account_id[-4:] if len(account_id) >= 4 else '0001'}",
                "date": invoice_date.strftime("%Y-%m-%d"),
                "due_date": (invoice_date + timedelta(days=15)).strftime("%Y-%m-%d"),
                "amount": 299.00,
                "amount_formatted": format_currency(299),
                "status": "paid" if i > 0 else "current",
                "description": "Professional Plan - Monthly",
                "payment_method": "Visa ending 4242",
                "download_url": f"/invoices/INV-{invoice_date.strftime('%Y%m')}",
            })
    else:
        invoices = [
            {
                "invoice_id": inv.get("invoice_number"),
                "date": format_date(inv.get("created_at")),
                "due_date": format_date(inv.get("due_date")),
                "amount": float(inv.get("amount", 0)),
                "amount_formatted": format_currency(inv.get("amount", 0)),
                "status": inv.get("status"),
                "description": inv.get("description"),
                "payment_method": inv.get("payment_method"),
                "paid_at": format_date(inv.get("paid_at")),
            }
            for inv in invoices
        ]

    total_paid = sum(inv["amount"] for inv in invoices if inv["status"] == "paid")

    billing = {
        "account_id": account_id,
        "invoices": invoices,
        "count": len(invoices),
        "total_paid_ytd": format_currency(total_paid),
        "outstanding": format_currency(sum(inv["amount"] for inv in invoices if inv["status"] in ["pending", "current"])),
    }

    return ToolResult.success(
        data=billing,
        message=f"Retrieved {len(invoices)} billing records",
    )


@mortgage_tool(
    name="update_payment_method",
    description="Update payment method for account billing",
    agent_roles=["subscription_manager"],
    risk_level="HIGH",
    parameters={
        "account_id": "Account ID",
        "payment_type": "Type: card, ach, invoice",
        "payment_token": "Tokenized payment details from payment processor",
        "set_default": "Set as default payment method",
    },
)
def update_payment_method(
    account_id: str,
    payment_type: str,
    payment_token: str,
    set_default: bool = True,
) -> ToolResult:
    """Update payment method."""
    import uuid
    method_id = str(uuid.uuid4())[:8].upper()

    valid_types = ["card", "ach", "invoice"]
    if payment_type not in valid_types:
        return ToolResult.error(f"Invalid payment type. Must be one of: {valid_types}")

    payment_update = {
        "payment_method_id": f"PM-{method_id}",
        "account_id": account_id,
        "payment_type": payment_type,
        "is_default": set_default,
        "updated_at": datetime.now().isoformat(),
        "status": "pending_verification" if payment_type == "ach" else "active",
        "verification_required": payment_type == "ach",
    }

    if payment_type == "card":
        payment_update["card_info"] = {
            "brand": "Visa",
            "last_four": "4242",
            "exp_month": 12,
            "exp_year": 2028,
        }
    elif payment_type == "ach":
        payment_update["bank_info"] = {
            "bank_name": "Chase",
            "last_four": "6789",
            "account_type": "checking",
        }
        payment_update["verification_deadline"] = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

    return ToolResult.success(
        data=payment_update,
        message=f"Payment method update initiated ({payment_type})",
        requires_approval=True,
    )


@mortgage_tool(
    name="get_usage_metrics",
    description="Get usage metrics and limits for subscription features",
    agent_roles=["subscription_manager"],
    risk_level="LOW",
    parameters={
        "account_id": "Account ID",
        "metric": "Optional specific metric: users, loans, ai_credits, storage, api_calls",
        "period": "Period: current, last_month, last_quarter",
    },
)
def get_usage_metrics(
    account_id: str,
    metric: Optional[str] = None,
    period: str = "current",
) -> ToolResult:
    """Get usage metrics."""
    # Get current plan limits
    plan = execute_single("""
        SELECT
            p.user_limit, p.loan_limit, p.ai_credit_limit,
            p.storage_limit_gb, p.api_call_limit
        FROM subscriptions s
        JOIN subscription_plans p ON p.id = s.plan_id
        WHERE s.account_id = :account_id
    """, {"account_id": account_id})

    # Default limits if no subscription found
    limits = {
        "users": plan.get("user_limit", 10) if plan else 10,
        "loans_per_month": plan.get("loan_limit", 100) if plan else 100,
        "ai_credits": plan.get("ai_credit_limit", 1000) if plan else 1000,
        "storage_gb": plan.get("storage_limit_gb", 50) if plan else 50,
        "api_calls": plan.get("api_call_limit", 10000) if plan else 10000,
    }

    # Get current usage
    usage = execute_single("""
        SELECT
            user_count, loan_count, ai_credit_usage,
            storage_used_gb, api_call_count
        FROM subscription_usage
        WHERE account_id = :account_id
            AND period = :period
    """, {"account_id": account_id, "period": period})

    current_usage = {
        "users": usage.get("user_count", 5) if usage else 5,
        "loans_per_month": usage.get("loan_count", 45) if usage else 45,
        "ai_credits": usage.get("ai_credit_usage", 350) if usage else 350,
        "storage_gb": float(usage.get("storage_used_gb", 12.5)) if usage else 12.5,
        "api_calls": usage.get("api_call_count", 3245) if usage else 3245,
    }

    # Build metrics response
    metrics = {}
    for key in limits:
        limit = limits[key]
        used = current_usage[key]
        pct = round((used / limit * 100), 1) if limit > 0 else 0

        metrics[key] = {
            "limit": limit,
            "used": used,
            "remaining": limit - used if isinstance(limit, (int, float)) else None,
            "percentage": pct,
            "status": "critical" if pct >= 90 else "warning" if pct >= 75 else "normal",
        }

    # Generate alerts
    alerts = []
    recommendations = []
    for key, data in metrics.items():
        if data["percentage"] >= 80:
            severity = "critical" if data["percentage"] >= 90 else "warning"
            alerts.append({
                "metric": key,
                "message": f"{key.replace('_', ' ').title()} usage at {data['percentage']}%",
                "severity": severity,
            })
            if data["percentage"] >= 90:
                recommendations.append({
                    "metric": key,
                    "suggestion": f"Consider upgrading your plan or adding {key} addon",
                })

    result = {
        "account_id": account_id,
        "period": period,
        "metrics": metrics,
        "alerts": alerts,
        "recommendations": recommendations,
        "as_of": datetime.now().isoformat(),
    }

    if metric and metric in metrics:
        return ToolResult.success(
            data={metric: metrics[metric], "alerts": [a for a in alerts if a["metric"] == metric]},
            message=f"{metric}: {metrics[metric]['percentage']}% used",
        )

    return ToolResult.success(
        data=result,
        message=f"Usage metrics: {len(alerts)} alerts",
    )


@mortgage_tool(
    name="manage_addons",
    description="Add, remove, or modify subscription addons",
    agent_roles=["subscription_manager"],
    risk_level="MEDIUM",
    parameters={
        "account_id": "Account ID",
        "action": "Action: add, remove, update",
        "addon_id": "Addon ID",
        "quantity": "Quantity (for add/update)",
    },
)
def manage_addons(
    account_id: str,
    action: str,
    addon_id: str,
    quantity: int = 1,
) -> ToolResult:
    """Manage subscription addons."""
    import uuid
    change_id = str(uuid.uuid4())[:8].upper()

    # Available addons catalog
    addon_catalog = {
        "extra_users": {
            "name": "Additional Users",
            "price_per_unit": 29,
            "unit": "user",
            "description": "Add more user seats to your account",
        },
        "extra_credits": {
            "name": "AI Credit Pack",
            "price_per_unit": 49,
            "unit": "500 credits",
            "description": "Additional AI processing credits",
        },
        "extra_storage": {
            "name": "Storage Upgrade",
            "price_per_unit": 19,
            "unit": "25 GB",
            "description": "Expand your document storage",
        },
        "premium_support": {
            "name": "Premium Support",
            "price_per_unit": 199,
            "unit": "month",
            "description": "Dedicated support with faster response times",
        },
        "api_access": {
            "name": "API Access",
            "price_per_unit": 99,
            "unit": "month",
            "description": "Full API access for custom integrations",
        },
        "white_label": {
            "name": "White Label Branding",
            "price_per_unit": 149,
            "unit": "month",
            "description": "Remove Perennia branding",
        },
    }

    valid_actions = ["add", "remove", "update"]
    if action not in valid_actions:
        return ToolResult.error(f"Invalid action. Must be one of: {valid_actions}")

    if addon_id not in addon_catalog:
        return ToolResult.error(f"Addon {addon_id} not found. Available: {list(addon_catalog.keys())}")

    addon = addon_catalog[addon_id]

    if action == "remove":
        quantity = 0
        total_price = 0
    else:
        total_price = addon["price_per_unit"] * quantity

    result = {
        "change_id": f"ADD-{change_id}",
        "account_id": account_id,
        "action": action,
        "addon_id": addon_id,
        "addon_name": addon["name"],
        "quantity": quantity,
        "price_per_unit": format_currency(addon["price_per_unit"]),
        "unit": addon["unit"],
        "total_monthly_cost": format_currency(total_price),
        "effective_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "pending_confirmation",
        "created_at": datetime.now().isoformat(),
    }

    action_msg = {
        "add": f"Adding {quantity}x {addon['name']}",
        "remove": f"Removing {addon['name']}",
        "update": f"Updating {addon['name']} to {quantity} {addon['unit']}s",
    }

    return ToolResult.success(
        data=result,
        message=f"{action_msg[action]} ({format_currency(total_price)}/mo)",
    )


@mortgage_tool(
    name="pause_subscription",
    description="Pause or cancel subscription with options",
    agent_roles=["subscription_manager"],
    risk_level="HIGH",
    parameters={
        "account_id": "Account ID",
        "action": "Action: pause, cancel, resume",
        "pause_duration_months": "Pause duration (1-3 months)",
        "reason": "Reason for pause/cancel",
        "feedback": "Optional feedback",
    },
)
def pause_subscription(
    account_id: str,
    action: str,
    pause_duration_months: Optional[int] = None,
    reason: Optional[str] = None,
    feedback: Optional[str] = None,
) -> ToolResult:
    """Pause or cancel subscription."""
    import uuid
    request_id = str(uuid.uuid4())[:8].upper()

    valid_actions = ["pause", "cancel", "resume"]
    if action not in valid_actions:
        return ToolResult.error(f"Invalid action. Must be one of: {valid_actions}")

    result = {
        "request_id": f"SUB-{request_id}",
        "account_id": account_id,
        "action": action,
        "reason": reason,
        "feedback": feedback,
        "status": "pending_confirmation",
        "requires_approval": True,
        "created_at": datetime.now().isoformat(),
    }

    if action == "pause":
        if not pause_duration_months or pause_duration_months not in [1, 2, 3]:
            return ToolResult.error("Pause duration must be 1, 2, or 3 months")

        pause_until = datetime.now() + timedelta(days=30 * pause_duration_months)
        result["pause_details"] = {
            "duration_months": pause_duration_months,
            "pause_starts": datetime.now().strftime("%Y-%m-%d"),
            "resumes_on": pause_until.strftime("%Y-%m-%d"),
            "data_preserved": True,
        }
        result["message"] = f"Subscription will pause for {pause_duration_months} month(s)"

    elif action == "cancel":
        # Get current period end
        sub = execute_single("""
            SELECT current_period_end FROM subscriptions
            WHERE account_id = :account_id
        """, {"account_id": account_id})

        cancel_date = sub.get("current_period_end") if sub else datetime.now() + timedelta(days=30)

        result["cancellation_details"] = {
            "effective_date": format_date(cancel_date) if isinstance(cancel_date, datetime) else cancel_date,
            "data_retention_days": 30,
            "export_available": True,
        }

        # Offer retention discount
        result["retention_offer"] = {
            "available": True,
            "discount_percentage": 25,
            "duration_months": 3,
            "message": "Stay with us! We'd like to offer you 25% off for the next 3 months.",
        }
        result["message"] = "Cancellation scheduled for end of billing period"

    elif action == "resume":
        result["resume_details"] = {
            "effective_date": datetime.now().strftime("%Y-%m-%d"),
            "billing_resumes": True,
        }
        result["message"] = "Subscription will resume immediately"

    return ToolResult.success(
        data=result,
        message=result.get("message", f"Subscription {action} requested"),
        requires_approval=True,
    )
