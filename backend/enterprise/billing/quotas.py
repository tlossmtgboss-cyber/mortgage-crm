"""
Tenant Billing and Quota Management for Mortgage CRM

Features:
- Usage-based billing with tiered pricing
- Resource quota enforcement
- Real-time usage tracking
- Automated billing cycles
- Invoice generation
- Overage handling
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BillingPeriod(str, Enum):
    """Billing period options."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class UsageMetric(str, Enum):
    """Trackable usage metrics."""
    USERS = "users"
    LOANS_PROCESSED = "loans_processed"
    API_CALLS = "api_calls"
    STORAGE_GB = "storage_gb"
    AI_UNDERWRITING_CALLS = "ai_underwriting_calls"
    DOCUMENT_PAGES = "document_pages"
    SMS_SENT = "sms_sent"
    EMAILS_SENT = "emails_sent"


class InvoiceStatus(str, Enum):
    """Invoice status."""
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


@dataclass
class PricingTier:
    """Pricing tier definition."""
    tier_id: str
    name: str
    base_price: Decimal
    billing_period: BillingPeriod

    # Included amounts
    included_users: int
    included_loans: int
    included_api_calls: int
    included_storage_gb: int
    included_ai_calls: int

    # Overage pricing (per unit)
    overage_user_price: Decimal = Decimal("25.00")
    overage_loan_price: Decimal = Decimal("5.00")
    overage_api_call_price: Decimal = Decimal("0.001")
    overage_storage_price: Decimal = Decimal("0.10")  # per GB
    overage_ai_call_price: Decimal = Decimal("0.50")

    # Features
    features: List[str] = field(default_factory=list)


@dataclass
class UsageRecord:
    """Record of resource usage."""
    id: str
    tenant_id: str
    metric: UsageMetric
    quantity: int
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuotaLimit:
    """Quota limit definition."""
    metric: UsageMetric
    limit: int
    period: str  # "monthly", "daily", "hourly"
    soft_limit_pct: float = 0.8  # Warn at 80%
    hard_limit_action: str = "block"  # "block", "allow_overage", "throttle"


@dataclass
class QuotaStatus:
    """Current quota status for a tenant."""
    tenant_id: str
    metric: UsageMetric
    current_usage: int
    limit: int
    remaining: int
    utilization_pct: float
    reset_at: datetime
    is_exceeded: bool = False
    is_near_limit: bool = False


@dataclass
class Invoice:
    """Billing invoice."""
    invoice_id: str
    tenant_id: str
    billing_period_start: datetime
    billing_period_end: datetime
    status: InvoiceStatus

    # Line items
    base_charge: Decimal
    overage_charges: Dict[str, Decimal]
    credits: Decimal
    tax: Decimal
    total: Decimal

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    due_date: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None

    line_items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Subscription:
    """Tenant subscription."""
    subscription_id: str
    tenant_id: str
    tier: PricingTier
    status: str  # active, cancelled, past_due, trialing

    # Dates
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    cancelled_at: Optional[datetime] = None
    trial_end: Optional[datetime] = None

    # Billing
    payment_method_id: Optional[str] = None
    auto_renew: bool = True

    # Custom overrides
    custom_limits: Dict[UsageMetric, int] = field(default_factory=dict)
    custom_pricing: Dict[str, Decimal] = field(default_factory=dict)
    discount_pct: float = 0.0


# Default pricing tiers
PRICING_TIERS = {
    "starter": PricingTier(
        tier_id="starter",
        name="Starter",
        base_price=Decimal("199.00"),
        billing_period=BillingPeriod.MONTHLY,
        included_users=5,
        included_loans=50,
        included_api_calls=10000,
        included_storage_gb=5,
        included_ai_calls=100,
        features=["lead_management", "loan_processing", "basic_reporting"],
    ),
    "professional": PricingTier(
        tier_id="professional",
        name="Professional",
        base_price=Decimal("499.00"),
        billing_period=BillingPeriod.MONTHLY,
        included_users=25,
        included_loans=500,
        included_api_calls=100000,
        included_storage_gb=50,
        included_ai_calls=1000,
        features=[
            "lead_management", "loan_processing", "advanced_reporting",
            "api_access", "workflow_automation", "email_integration",
        ],
    ),
    "enterprise": PricingTier(
        tier_id="enterprise",
        name="Enterprise",
        base_price=Decimal("1499.00"),
        billing_period=BillingPeriod.MONTHLY,
        included_users=100,
        included_loans=5000,
        included_api_calls=1000000,
        included_storage_gb=500,
        included_ai_calls=10000,
        features=[
            "lead_management", "loan_processing", "advanced_reporting",
            "api_access", "workflow_automation", "email_integration",
            "ai_underwriting", "custom_branding", "sso_saml",
            "audit_logging", "compliance_monitoring", "multi_branch",
        ],
    ),
}


class UsageTracker:
    """Track and aggregate usage metrics."""

    def __init__(self):
        self._usage_records: List[UsageRecord] = []
        self._aggregated_usage: Dict[str, Dict[UsageMetric, int]] = {}

    def record_usage(
        self,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int = 1,
        metadata: Dict[str, Any] = None
    ) -> UsageRecord:
        """Record a usage event."""
        record = UsageRecord(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            metric=metric,
            quantity=quantity,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

        self._usage_records.append(record)
        self._update_aggregation(tenant_id, metric, quantity)

        return record

    def _update_aggregation(
        self,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int
    ) -> None:
        """Update aggregated usage."""
        if tenant_id not in self._aggregated_usage:
            self._aggregated_usage[tenant_id] = {}

        current = self._aggregated_usage[tenant_id].get(metric, 0)
        self._aggregated_usage[tenant_id][metric] = current + quantity

    def get_usage(
        self,
        tenant_id: str,
        metric: UsageMetric,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> int:
        """Get usage for a specific metric and period."""
        if start_date is None and end_date is None:
            return self._aggregated_usage.get(tenant_id, {}).get(metric, 0)

        total = 0
        for record in self._usage_records:
            if record.tenant_id != tenant_id or record.metric != metric:
                continue

            if start_date and record.timestamp < start_date:
                continue
            if end_date and record.timestamp > end_date:
                continue

            total += record.quantity

        return total

    def get_all_usage(
        self,
        tenant_id: str,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> Dict[UsageMetric, int]:
        """Get all usage metrics for a tenant."""
        usage = {}
        for metric in UsageMetric:
            usage[metric] = self.get_usage(tenant_id, metric, start_date, end_date)
        return usage

    def reset_period(self, tenant_id: str) -> None:
        """Reset usage for new billing period."""
        self._aggregated_usage[tenant_id] = {}


class QuotaManager:
    """Manage and enforce resource quotas."""

    def __init__(self, usage_tracker: UsageTracker):
        self.usage_tracker = usage_tracker
        self._quotas: Dict[str, List[QuotaLimit]] = {}
        self._quota_overrides: Dict[str, Dict[UsageMetric, int]] = {}

    def set_quota(
        self,
        tenant_id: str,
        quotas: List[QuotaLimit]
    ) -> None:
        """Set quotas for a tenant."""
        self._quotas[tenant_id] = quotas

    def set_quota_override(
        self,
        tenant_id: str,
        metric: UsageMetric,
        limit: int
    ) -> None:
        """Set custom quota override for a tenant."""
        if tenant_id not in self._quota_overrides:
            self._quota_overrides[tenant_id] = {}
        self._quota_overrides[tenant_id][metric] = limit

    def check_quota(
        self,
        tenant_id: str,
        metric: UsageMetric,
        requested_quantity: int = 1
    ) -> Tuple[bool, QuotaStatus]:
        """Check if quota allows the requested usage."""
        quotas = self._quotas.get(tenant_id, [])
        quota = next((q for q in quotas if q.metric == metric), None)

        if not quota:
            # No quota defined, allow
            return True, None

        # Get effective limit (check for override)
        limit = self._quota_overrides.get(tenant_id, {}).get(metric, quota.limit)

        # Get current usage
        current_usage = self.usage_tracker.get_usage(tenant_id, metric)
        would_use = current_usage + requested_quantity

        status = QuotaStatus(
            tenant_id=tenant_id,
            metric=metric,
            current_usage=current_usage,
            limit=limit,
            remaining=max(0, limit - current_usage),
            utilization_pct=(current_usage / limit * 100) if limit > 0 else 0,
            reset_at=self._get_reset_time(quota.period),
            is_exceeded=would_use > limit,
            is_near_limit=(current_usage / limit) >= quota.soft_limit_pct if limit > 0 else False,
        )

        # Check if quota would be exceeded
        if would_use > limit:
            if quota.hard_limit_action == "block":
                return False, status
            elif quota.hard_limit_action == "throttle":
                # Log warning but allow
                logger.warning(f"Quota exceeded for {tenant_id}/{metric}: {would_use}/{limit}")

        return True, status

    def _get_reset_time(self, period: str) -> datetime:
        """Get next quota reset time."""
        now = datetime.utcnow()

        if period == "hourly":
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        elif period == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif period == "monthly":
            if now.month == 12:
                return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        return now + timedelta(days=30)

    def get_all_quota_status(self, tenant_id: str) -> List[QuotaStatus]:
        """Get status of all quotas for a tenant."""
        statuses = []
        quotas = self._quotas.get(tenant_id, [])

        for quota in quotas:
            _, status = self.check_quota(tenant_id, quota.metric, 0)
            if status:
                statuses.append(status)

        return statuses


class BillingEngine:
    """Handle billing calculations and invoice generation."""

    def __init__(
        self,
        usage_tracker: UsageTracker,
        tax_rate: float = 0.0
    ):
        self.usage_tracker = usage_tracker
        self.tax_rate = tax_rate
        self._subscriptions: Dict[str, Subscription] = {}
        self._invoices: Dict[str, Invoice] = {}

    def create_subscription(
        self,
        tenant_id: str,
        tier_id: str,
        payment_method_id: str = None,
        trial_days: int = 0
    ) -> Subscription:
        """Create a new subscription."""
        tier = PRICING_TIERS.get(tier_id)
        if not tier:
            raise ValueError(f"Unknown tier: {tier_id}")

        now = datetime.utcnow()
        period_end = self._calculate_period_end(now, tier.billing_period)

        subscription = Subscription(
            subscription_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            tier=tier,
            status="trialing" if trial_days > 0 else "active",
            start_date=now,
            current_period_start=now,
            current_period_end=period_end,
            trial_end=now + timedelta(days=trial_days) if trial_days > 0 else None,
            payment_method_id=payment_method_id,
        )

        self._subscriptions[tenant_id] = subscription
        return subscription

    def _calculate_period_end(
        self,
        start: datetime,
        period: BillingPeriod
    ) -> datetime:
        """Calculate billing period end date."""
        if period == BillingPeriod.MONTHLY:
            if start.month == 12:
                return start.replace(year=start.year + 1, month=1)
            return start.replace(month=start.month + 1)
        elif period == BillingPeriod.QUARTERLY:
            month = start.month + 3
            year = start.year
            if month > 12:
                month -= 12
                year += 1
            return start.replace(year=year, month=month)
        else:  # Annual
            return start.replace(year=start.year + 1)

    def calculate_charges(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, Any]:
        """Calculate charges for a billing period."""
        subscription = self._subscriptions.get(tenant_id)
        if not subscription:
            raise ValueError(f"No subscription for tenant: {tenant_id}")

        tier = subscription.tier
        usage = self.usage_tracker.get_all_usage(tenant_id, period_start, period_end)

        # Base charge
        base_charge = tier.base_price

        # Apply discount
        if subscription.discount_pct > 0:
            base_charge = base_charge * Decimal(1 - subscription.discount_pct)

        # Calculate overages
        overage_charges = {}
        line_items = [
            {
                "description": f"{tier.name} Plan - {tier.billing_period.value}",
                "quantity": 1,
                "unit_price": tier.base_price,
                "amount": base_charge,
            }
        ]

        # Users overage
        user_overage = max(0, usage.get(UsageMetric.USERS, 0) - tier.included_users)
        if user_overage > 0:
            charge = Decimal(user_overage) * tier.overage_user_price
            overage_charges["users"] = charge
            line_items.append({
                "description": f"Additional users ({user_overage})",
                "quantity": user_overage,
                "unit_price": tier.overage_user_price,
                "amount": charge,
            })

        # Loans overage
        loan_overage = max(0, usage.get(UsageMetric.LOANS_PROCESSED, 0) - tier.included_loans)
        if loan_overage > 0:
            charge = Decimal(loan_overage) * tier.overage_loan_price
            overage_charges["loans"] = charge
            line_items.append({
                "description": f"Additional loans processed ({loan_overage})",
                "quantity": loan_overage,
                "unit_price": tier.overage_loan_price,
                "amount": charge,
            })

        # API calls overage
        api_overage = max(0, usage.get(UsageMetric.API_CALLS, 0) - tier.included_api_calls)
        if api_overage > 0:
            charge = Decimal(api_overage) * tier.overage_api_call_price
            overage_charges["api_calls"] = charge
            line_items.append({
                "description": f"Additional API calls ({api_overage:,})",
                "quantity": api_overage,
                "unit_price": tier.overage_api_call_price,
                "amount": charge,
            })

        # Storage overage
        storage_overage = max(0, usage.get(UsageMetric.STORAGE_GB, 0) - tier.included_storage_gb)
        if storage_overage > 0:
            charge = Decimal(storage_overage) * tier.overage_storage_price
            overage_charges["storage"] = charge
            line_items.append({
                "description": f"Additional storage ({storage_overage} GB)",
                "quantity": storage_overage,
                "unit_price": tier.overage_storage_price,
                "amount": charge,
            })

        # AI calls overage
        ai_overage = max(0, usage.get(UsageMetric.AI_UNDERWRITING_CALLS, 0) - tier.included_ai_calls)
        if ai_overage > 0:
            charge = Decimal(ai_overage) * tier.overage_ai_call_price
            overage_charges["ai_calls"] = charge
            line_items.append({
                "description": f"Additional AI underwriting calls ({ai_overage})",
                "quantity": ai_overage,
                "unit_price": tier.overage_ai_call_price,
                "amount": charge,
            })

        # Calculate totals
        subtotal = base_charge + sum(overage_charges.values())
        tax = subtotal * Decimal(self.tax_rate)
        total = subtotal + tax

        return {
            "base_charge": base_charge,
            "overage_charges": overage_charges,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "line_items": line_items,
            "usage": {k.value: v for k, v in usage.items()},
        }

    def generate_invoice(
        self,
        tenant_id: str,
        period_start: datetime = None,
        period_end: datetime = None
    ) -> Invoice:
        """Generate an invoice for a billing period."""
        subscription = self._subscriptions.get(tenant_id)
        if not subscription:
            raise ValueError(f"No subscription for tenant: {tenant_id}")

        # Use current period if not specified
        if not period_start:
            period_start = subscription.current_period_start
        if not period_end:
            period_end = subscription.current_period_end

        # Calculate charges
        charges = self.calculate_charges(tenant_id, period_start, period_end)

        # Create invoice
        invoice = Invoice(
            invoice_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            billing_period_start=period_start,
            billing_period_end=period_end,
            status=InvoiceStatus.PENDING,
            base_charge=charges["base_charge"],
            overage_charges=charges["overage_charges"],
            credits=Decimal("0"),
            tax=charges["tax"],
            total=charges["total"],
            due_date=datetime.utcnow() + timedelta(days=30),
            line_items=charges["line_items"],
        )

        self._invoices[invoice.invoice_id] = invoice

        logger.info(f"Generated invoice {invoice.invoice_id} for tenant {tenant_id}: ${invoice.total}")
        return invoice

    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Get invoice by ID."""
        return self._invoices.get(invoice_id)

    def get_tenant_invoices(
        self,
        tenant_id: str,
        status: InvoiceStatus = None
    ) -> List[Invoice]:
        """Get all invoices for a tenant."""
        invoices = [i for i in self._invoices.values() if i.tenant_id == tenant_id]

        if status:
            invoices = [i for i in invoices if i.status == status]

        return sorted(invoices, key=lambda i: i.created_at, reverse=True)

    def record_payment(
        self,
        invoice_id: str,
        payment_method: str,
        transaction_id: str = None
    ) -> Invoice:
        """Record payment for an invoice."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice not found: {invoice_id}")

        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.utcnow()
        invoice.payment_method = payment_method

        logger.info(f"Payment recorded for invoice {invoice_id}")
        return invoice

    def process_renewals(self) -> List[Invoice]:
        """Process subscription renewals and generate invoices."""
        now = datetime.utcnow()
        invoices = []

        for tenant_id, subscription in self._subscriptions.items():
            if subscription.status != "active":
                continue

            if subscription.current_period_end <= now:
                # Generate invoice for past period
                invoice = self.generate_invoice(tenant_id)
                invoices.append(invoice)

                # Start new period
                subscription.current_period_start = subscription.current_period_end
                subscription.current_period_end = self._calculate_period_end(
                    subscription.current_period_start,
                    subscription.tier.billing_period
                )

                # Reset usage
                self.usage_tracker.reset_period(tenant_id)

        return invoices


class BillingService:
    """High-level billing service coordinating all components."""

    def __init__(self, tax_rate: float = 0.0):
        self.usage_tracker = UsageTracker()
        self.quota_manager = QuotaManager(self.usage_tracker)
        self.billing_engine = BillingEngine(self.usage_tracker, tax_rate)

    def provision_tenant(
        self,
        tenant_id: str,
        tier_id: str,
        payment_method_id: str = None,
        trial_days: int = 14
    ) -> Dict[str, Any]:
        """Provision billing for a new tenant."""
        # Create subscription
        subscription = self.billing_engine.create_subscription(
            tenant_id=tenant_id,
            tier_id=tier_id,
            payment_method_id=payment_method_id,
            trial_days=trial_days,
        )

        # Set up quotas based on tier
        tier = subscription.tier
        quotas = [
            QuotaLimit(UsageMetric.USERS, tier.included_users, "monthly", hard_limit_action="allow_overage"),
            QuotaLimit(UsageMetric.LOANS_PROCESSED, tier.included_loans, "monthly", hard_limit_action="allow_overage"),
            QuotaLimit(UsageMetric.API_CALLS, tier.included_api_calls, "monthly", hard_limit_action="throttle"),
            QuotaLimit(UsageMetric.STORAGE_GB, tier.included_storage_gb, "monthly", hard_limit_action="block"),
            QuotaLimit(UsageMetric.AI_UNDERWRITING_CALLS, tier.included_ai_calls, "monthly", hard_limit_action="allow_overage"),
        ]
        self.quota_manager.set_quota(tenant_id, quotas)

        return {
            "subscription": subscription,
            "quotas": quotas,
            "trial_ends": subscription.trial_end,
        }

    def record_usage(
        self,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int = 1,
        metadata: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[QuotaStatus]]:
        """Record usage and check quota."""
        # Check quota first
        allowed, status = self.quota_manager.check_quota(tenant_id, metric, quantity)

        if not allowed:
            logger.warning(f"Quota exceeded for {tenant_id}/{metric}")
            return False, status

        # Record the usage
        self.usage_tracker.record_usage(tenant_id, metric, quantity, metadata)

        return True, status

    def get_usage_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get usage summary for tenant."""
        subscription = self.billing_engine._subscriptions.get(tenant_id)
        if not subscription:
            return {}

        usage = self.usage_tracker.get_all_usage(
            tenant_id,
            subscription.current_period_start,
            subscription.current_period_end
        )

        tier = subscription.tier
        quotas = self.quota_manager.get_all_quota_status(tenant_id)

        return {
            "tenant_id": tenant_id,
            "tier": tier.name,
            "period": {
                "start": subscription.current_period_start.isoformat(),
                "end": subscription.current_period_end.isoformat(),
            },
            "usage": {
                "users": {
                    "current": usage.get(UsageMetric.USERS, 0),
                    "included": tier.included_users,
                    "overage": max(0, usage.get(UsageMetric.USERS, 0) - tier.included_users),
                },
                "loans": {
                    "current": usage.get(UsageMetric.LOANS_PROCESSED, 0),
                    "included": tier.included_loans,
                    "overage": max(0, usage.get(UsageMetric.LOANS_PROCESSED, 0) - tier.included_loans),
                },
                "api_calls": {
                    "current": usage.get(UsageMetric.API_CALLS, 0),
                    "included": tier.included_api_calls,
                    "overage": max(0, usage.get(UsageMetric.API_CALLS, 0) - tier.included_api_calls),
                },
                "storage_gb": {
                    "current": usage.get(UsageMetric.STORAGE_GB, 0),
                    "included": tier.included_storage_gb,
                    "overage": max(0, usage.get(UsageMetric.STORAGE_GB, 0) - tier.included_storage_gb),
                },
                "ai_calls": {
                    "current": usage.get(UsageMetric.AI_UNDERWRITING_CALLS, 0),
                    "included": tier.included_ai_calls,
                    "overage": max(0, usage.get(UsageMetric.AI_UNDERWRITING_CALLS, 0) - tier.included_ai_calls),
                },
            },
            "quotas": [
                {
                    "metric": q.metric.value,
                    "current": q.current_usage,
                    "limit": q.limit,
                    "utilization_pct": q.utilization_pct,
                    "is_near_limit": q.is_near_limit,
                    "is_exceeded": q.is_exceeded,
                }
                for q in quotas
            ],
            "estimated_charges": self.billing_engine.calculate_charges(
                tenant_id,
                subscription.current_period_start,
                subscription.current_period_end
            ),
        }

    def upgrade_tier(
        self,
        tenant_id: str,
        new_tier_id: str,
        prorate: bool = True
    ) -> Dict[str, Any]:
        """Upgrade tenant to a new tier."""
        subscription = self.billing_engine._subscriptions.get(tenant_id)
        if not subscription:
            raise ValueError(f"No subscription for tenant: {tenant_id}")

        new_tier = PRICING_TIERS.get(new_tier_id)
        if not new_tier:
            raise ValueError(f"Unknown tier: {new_tier_id}")

        old_tier = subscription.tier

        # Calculate proration if applicable
        proration_credit = Decimal("0")
        if prorate:
            now = datetime.utcnow()
            total_days = (subscription.current_period_end - subscription.current_period_start).days
            remaining_days = (subscription.current_period_end - now).days

            if remaining_days > 0 and total_days > 0:
                daily_rate = old_tier.base_price / Decimal(total_days)
                proration_credit = daily_rate * Decimal(remaining_days)

        # Update subscription
        subscription.tier = new_tier

        # Update quotas
        quotas = [
            QuotaLimit(UsageMetric.USERS, new_tier.included_users, "monthly", hard_limit_action="allow_overage"),
            QuotaLimit(UsageMetric.LOANS_PROCESSED, new_tier.included_loans, "monthly", hard_limit_action="allow_overage"),
            QuotaLimit(UsageMetric.API_CALLS, new_tier.included_api_calls, "monthly", hard_limit_action="throttle"),
            QuotaLimit(UsageMetric.STORAGE_GB, new_tier.included_storage_gb, "monthly", hard_limit_action="block"),
            QuotaLimit(UsageMetric.AI_UNDERWRITING_CALLS, new_tier.included_ai_calls, "monthly", hard_limit_action="allow_overage"),
        ]
        self.quota_manager.set_quota(tenant_id, quotas)

        logger.info(f"Upgraded tenant {tenant_id} from {old_tier.name} to {new_tier.name}")

        return {
            "old_tier": old_tier.name,
            "new_tier": new_tier.name,
            "proration_credit": float(proration_credit),
            "new_quotas": quotas,
        }
