"""
Subscription Manager Agent

Specialized agent for SaaS subscription and billing management with 8 tools:
1. get_subscription_status - Get current subscription details
2. list_available_plans - List available subscription plans
3. upgrade_subscription - Upgrade to a higher plan
4. downgrade_subscription - Downgrade to a lower plan
5. get_billing_history - Get billing history
6. update_payment_method - Update payment method
7. calculate_proration - Calculate proration for plan changes
8. cancel_subscription - Cancel subscription
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class SubscriptionStatusInput(BaseModel):
    organization_id: Optional[int] = Field(None, description="Organization ID")


class AvailablePlansInput(BaseModel):
    include_enterprise: bool = Field(default=False, description="Include enterprise plans")


class UpgradeInput(BaseModel):
    new_plan: str = Field(..., description="Plan to upgrade to")
    billing_cycle: str = Field(default="monthly", description="Billing cycle: monthly, annual")


class DowngradeInput(BaseModel):
    new_plan: str = Field(..., description="Plan to downgrade to")
    effective_date: Optional[str] = Field(None, description="When downgrade takes effect")


class BillingHistoryInput(BaseModel):
    limit: int = Field(default=12, description="Number of records to return")
    start_date: Optional[str] = Field(None, description="Start date filter")


class PaymentMethodInput(BaseModel):
    payment_type: str = Field(..., description="Payment type: card, ach, invoice")
    token: Optional[str] = Field(None, description="Payment token from processor")


class ProrationInput(BaseModel):
    from_plan: str = Field(..., description="Current plan")
    to_plan: str = Field(..., description="Target plan")
    effective_date: Optional[str] = Field(None, description="Change effective date")


class CancelInput(BaseModel):
    reason: str = Field(..., description="Cancellation reason")
    feedback: Optional[str] = Field(None, description="Additional feedback")
    immediate: bool = Field(default=False, description="Cancel immediately vs end of period")


# ============================================================================
# SUBSCRIPTION MANAGER AGENT
# ============================================================================

@AgentRegistry.register
class SubscriptionAgent(SpecializedAgent):
    """
    Subscription management agent for SaaS billing operations.

    Handles subscription lifecycle, billing, and plan management
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "SubscriptionAgent"

    @property
    def description(self) -> str:
        return "Manages subscriptions, billing, plan changes, and payment methods"

    def _register_tools(self):
        """Register all subscription management tools"""

        self.register_tool(AgentTool(
            name="get_subscription_status",
            description="Get current subscription status including plan, billing cycle, and usage",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_subscription_status,
            input_schema=SubscriptionStatusInput
        ))

        self.register_tool(AgentTool(
            name="list_available_plans",
            description="List all available subscription plans with features and pricing",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._list_available_plans,
            input_schema=AvailablePlansInput
        ))

        self.register_tool(AgentTool(
            name="upgrade_subscription",
            description="Upgrade subscription to a higher tier plan",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._upgrade_subscription,
            input_schema=UpgradeInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="downgrade_subscription",
            description="Downgrade subscription to a lower tier plan",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._downgrade_subscription,
            input_schema=DowngradeInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="get_billing_history",
            description="Get billing and payment history",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_billing_history,
            input_schema=BillingHistoryInput
        ))

        self.register_tool(AgentTool(
            name="update_payment_method",
            description="Update payment method for subscription",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._update_payment_method,
            input_schema=PaymentMethodInput,
            requires_confirmation=True
        ))

        self.register_tool(AgentTool(
            name="calculate_proration",
            description="Calculate prorated charges for plan changes",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_proration,
            input_schema=ProrationInput
        ))

        self.register_tool(AgentTool(
            name="cancel_subscription",
            description="Cancel subscription with optional feedback",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.CRITICAL,
            handler=self._cancel_subscription,
            input_schema=CancelInput,
            requires_confirmation=True
        ))

    async def _get_subscription_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get current subscription status"""
        org_id = self.require_org_id()

        # Simulated subscription data (would come from billing system scoped to org)
        subscription = {
            "organization_id": org_id,
            "plan": "professional",
            "status": "active",
            "billing_cycle": "monthly",
            "price": 299,
            "current_period_start": (datetime.now() - timedelta(days=15)).isoformat(),
            "current_period_end": (datetime.now() + timedelta(days=15)).isoformat(),
            "next_billing_date": (datetime.now() + timedelta(days=15)).isoformat(),
            "users": {
                "included": 5,
                "current": 3,
                "additional_cost": 49
            },
            "features": {
                "ai_assistant": True,
                "email_integration": True,
                "sms": True,
                "api_access": True,
                "custom_reports": True
            },
            "usage": {
                "loans_this_month": 45,
                "loan_limit": 100,
                "api_calls": 2500,
                "api_limit": 10000
            }
        }

        return ToolResult(
            success=True,
            data=subscription,
            message=f"Subscription: {subscription['plan']} (${subscription['price']}/mo)"
        )

    async def _list_available_plans(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """List available plans"""
        org_id = self.require_org_id()

        plans = [
            {
                "id": "starter",
                "name": "Starter",
                "price_monthly": 99,
                "price_annual": 990,
                "users_included": 1,
                "features": ["Basic CRM", "Lead Management", "Email Support"]
            },
            {
                "id": "professional",
                "name": "Professional",
                "price_monthly": 299,
                "price_annual": 2990,
                "users_included": 5,
                "features": ["All Starter features", "AI Assistant", "Email Integration", "SMS", "API Access"]
            },
            {
                "id": "team",
                "name": "Team",
                "price_monthly": 599,
                "price_annual": 5990,
                "users_included": 15,
                "features": ["All Professional features", "Advanced Analytics", "Custom Reports", "Priority Support"]
            }
        ]

        if input_data.get("include_enterprise"):
            plans.append({
                "id": "enterprise",
                "name": "Enterprise",
                "price_monthly": "Custom",
                "price_annual": "Custom",
                "users_included": "Unlimited",
                "features": ["All Team features", "Dedicated Support", "Custom Integrations", "SLA"]
            })

        return ToolResult(
            success=True,
            data={"plans": plans},
            message=f"Found {len(plans)} available plans"
        )

    async def _upgrade_subscription(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Upgrade subscription"""
        org_id = self.require_org_id()
        new_plan = input_data["new_plan"]
        billing_cycle = input_data.get("billing_cycle", "monthly")

        self.audit_log(
            action="upgrade_subscription",
            entity_type="subscription",
            details={"new_plan": new_plan, "billing_cycle": billing_cycle, "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "action": "upgrade",
                "organization_id": org_id,
                "new_plan": new_plan,
                "billing_cycle": billing_cycle,
                "effective_immediately": True,
                "proration_applied": True
            },
            message=f"Upgrade to {new_plan} plan initiated"
        )

    async def _downgrade_subscription(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Downgrade subscription"""
        org_id = self.require_org_id()

        self.audit_log(
            action="downgrade_subscription",
            entity_type="subscription",
            details={"new_plan": input_data["new_plan"], "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "action": "downgrade",
                "organization_id": org_id,
                "new_plan": input_data["new_plan"],
                "effective_date": input_data.get("effective_date") or "end_of_period"
            },
            message=f"Downgrade to {input_data['new_plan']} scheduled"
        )

    async def _get_billing_history(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Get billing history"""
        org_id = self.require_org_id()

        # Simulated billing history (would query billing records scoped to org)
        history = []
        for i in range(min(input_data.get("limit", 12), 12)):
            date = datetime.now() - timedelta(days=30 * i)
            history.append({
                "date": date.isoformat(),
                "description": "Professional Plan - Monthly",
                "amount": 299,
                "status": "paid",
                "invoice_id": f"INV-{date.strftime('%Y%m')}-001"
            })

        return ToolResult(
            success=True,
            data={"organization_id": org_id, "history": history, "total_records": len(history)},
            message=f"Retrieved {len(history)} billing records"
        )

    async def _update_payment_method(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Update payment method"""
        org_id = self.require_org_id()

        self.audit_log(
            action="update_payment_method",
            entity_type="payment_method",
            details={"payment_type": input_data["payment_type"], "organization_id": org_id}
        )

        return ToolResult(
            success=True,
            data={
                "organization_id": org_id,
                "payment_type": input_data["payment_type"],
                "updated": True,
                "verified": True
            },
            message="Payment method updated successfully"
        )

    async def _calculate_proration(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Calculate proration for plan change"""
        org_id = self.require_org_id()

        plan_prices = {"starter": 99, "professional": 299, "team": 599}

        from_price = plan_prices.get(input_data["from_plan"], 0)
        to_price = plan_prices.get(input_data["to_plan"], 0)

        days_remaining = 15  # Simulated
        daily_rate_from = from_price / 30
        daily_rate_to = to_price / 30

        credit = daily_rate_from * days_remaining
        charge = daily_rate_to * days_remaining
        net = charge - credit

        return ToolResult(
            success=True,
            data={
                "organization_id": org_id,
                "from_plan": input_data["from_plan"],
                "to_plan": input_data["to_plan"],
                "days_remaining": days_remaining,
                "credit_amount": round(credit, 2),
                "charge_amount": round(charge, 2),
                "net_charge": round(net, 2)
            },
            message=f"Net charge for plan change: ${net:.2f}"
        )

    async def _cancel_subscription(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Cancel subscription"""
        org_id = self.require_org_id()

        self.audit_log(
            action="cancel_subscription",
            entity_type="subscription",
            details={
                "reason": input_data["reason"],
                "immediate": input_data.get("immediate", False),
                "organization_id": org_id,
            }
        )

        return ToolResult(
            success=True,
            data={
                "action": "cancel",
                "organization_id": org_id,
                "reason": input_data["reason"],
                "feedback": input_data.get("feedback"),
                "effective": "immediate" if input_data.get("immediate") else "end_of_period",
                "cancellation_date": datetime.now().isoformat() if input_data.get("immediate") else (datetime.now() + timedelta(days=15)).isoformat()
            },
            message="Subscription cancellation initiated"
        )
