"""
Stripe Payment Integration Service

Handles subscription management, customer creation, and payment processing
for the mortgage CRM SaaS platform.
"""

import stripe
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

# Initialize Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')


class StripeService:
    """Service for managing Stripe subscriptions and payments"""

    # Subscription plan price IDs (set these in Stripe dashboard)
    PLANS = {
        "starter": {
            "name": "Starter",
            "price_monthly": 99,
            "stripe_price_id": os.getenv('STRIPE_STARTER_PRICE_ID', 'price_starter'),
            "features": [
                "Up to 5 team members",
                "1,000 leads per month",
                "Basic AI assistant",
                "Email support",
                "Calendar integration",
                "Task automation"
            ],
            "user_limit": 5
        },
        "professional": {
            "name": "Professional",
            "price_monthly": 199,
            "stripe_price_id": os.getenv('STRIPE_PRO_PRICE_ID', 'price_professional'),
            "features": [
                "Up to 15 team members",
                "Unlimited leads",
                "Advanced AI assistant with workflow automation",
                "Priority support",
                "Calendar + Email + Teams integration",
                "Custom workflows",
                "SMS notifications",
                "Analytics & reporting"
            ],
            "user_limit": 15
        },
        "enterprise": {
            "name": "Enterprise",
            "price_monthly": 399,
            "stripe_price_id": os.getenv('STRIPE_ENTERPRISE_PRICE_ID', 'price_enterprise'),
            "features": [
                "Unlimited team members",
                "Unlimited leads",
                "Full AI agent capabilities",
                "24/7 dedicated support",
                "All integrations",
                "Custom AI training",
                "White-label options",
                "API access",
                "Custom reporting"
            ],
            "user_limit": 999
        }
    }

    @staticmethod
    def create_customer(email: str, name: str, metadata: Dict = None) -> stripe.Customer:
        """
        Create a Stripe customer

        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata to attach

        Returns:
            Stripe Customer object
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata=metadata or {}
            )
            return customer
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create Stripe customer: {str(e)}")

    @staticmethod
    def create_subscription(
        customer_id: str,
        price_id: str,
        trial_days: int = 14
    ) -> stripe.Subscription:
        """
        Create a subscription for a customer

        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID for the plan
            trial_days: Number of trial days (default 14)

        Returns:
            Stripe Subscription object
        """
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                trial_period_days=trial_days,
                payment_behavior='default_incomplete',
                payment_settings={'save_default_payment_method': 'on_subscription'},
                expand=['latest_invoice.payment_intent']
            )
            return subscription
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create subscription: {str(e)}")

    @staticmethod
    def create_checkout_session(
        customer_email: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = 14,
        metadata: Dict = None
    ) -> stripe.checkout.Session:
        """
        Create a Stripe Checkout session for subscription signup

        Args:
            customer_email: Customer's email
            price_id: Stripe price ID
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            trial_days: Number of trial days
            metadata: Additional metadata

        Returns:
            Stripe Checkout Session object
        """
        try:
            session = stripe.checkout.Session.create(
                customer_email=customer_email,
                mode='subscription',
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                subscription_data={
                    'trial_period_days': trial_days,
                    'metadata': metadata or {}
                },
                success_url=success_url,
                cancel_url=cancel_url,
                allow_promotion_codes=True
            )
            return session
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create checkout session: {str(e)}")

    @staticmethod
    def get_subscription(subscription_id: str) -> stripe.Subscription:
        """Get subscription details"""
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to retrieve subscription: {str(e)}")

    @staticmethod
    def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> stripe.Subscription:
        """
        Cancel a subscription

        Args:
            subscription_id: Stripe subscription ID
            at_period_end: If True, cancel at end of billing period

        Returns:
            Updated Stripe Subscription object
        """
        try:
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                subscription = stripe.Subscription.delete(subscription_id)
            return subscription
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to cancel subscription: {str(e)}")

    @staticmethod
    def update_subscription(
        subscription_id: str,
        new_price_id: str
    ) -> stripe.Subscription:
        """
        Update subscription to a different plan

        Args:
            subscription_id: Stripe subscription ID
            new_price_id: New Stripe price ID

        Returns:
            Updated Stripe Subscription object
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)

            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False,
                proration_behavior='create_prorations',
                items=[{
                    'id': subscription['items']['data'][0].id,
                    'price': new_price_id,
                }]
            )
            return subscription
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to update subscription: {str(e)}")

    @staticmethod
    def create_customer_portal_session(
        customer_id: str,
        return_url: str
    ) -> stripe.billing_portal.Session:
        """
        Create a customer portal session for self-service billing management

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session

        Returns:
            Stripe billing portal Session object
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to create portal session: {str(e)}")

    @staticmethod
    def verify_webhook_signature(payload: bytes, sig_header: str) -> Dict:
        """
        Verify Stripe webhook signature and return the event

        Args:
            payload: Raw request body
            sig_header: Stripe signature header

        Returns:
            Stripe Event object
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            raise Exception("Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            raise Exception("Invalid signature")

    @staticmethod
    def get_payment_method(payment_method_id: str) -> stripe.PaymentMethod:
        """Get payment method details"""
        try:
            return stripe.PaymentMethod.retrieve(payment_method_id)
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to retrieve payment method: {str(e)}")

    @staticmethod
    def list_invoices(customer_id: str, limit: int = 10) -> List[stripe.Invoice]:
        """List invoices for a customer"""
        try:
            invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
            return invoices.data
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to list invoices: {str(e)}")

    @staticmethod
    def get_plan_info(plan_key: str) -> Optional[Dict]:
        """Get plan information by key"""
        return StripeService.PLANS.get(plan_key)

    @staticmethod
    def get_all_plans() -> List[Dict]:
        """Get all available subscription plans"""
        return [
            {
                "key": key,
                **plan_info
            }
            for key, plan_info in StripeService.PLANS.items()
        ]


# Webhook event handlers
class StripeWebhookHandlers:
    """Handlers for different Stripe webhook events"""

    @staticmethod
    def handle_checkout_completed(session: Dict, db: Session):
        """Handle successful checkout session"""
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        customer_email = session.get('customer_email')

        # Update user's subscription in database
        # This will be implemented when we connect to the User model
        print(f"Checkout completed: {customer_email}, subscription: {subscription_id}")

    @staticmethod
    def handle_subscription_created(subscription: Dict, db: Session):
        """Handle subscription creation"""
        customer_id = subscription.get('customer')
        subscription_id = subscription['id']
        status = subscription['status']

        print(f"Subscription created: {subscription_id}, status: {status}")

    @staticmethod
    def handle_subscription_updated(subscription: Dict, db: Session):
        """Handle subscription updates"""
        subscription_id = subscription['id']
        status = subscription['status']

        print(f"Subscription updated: {subscription_id}, status: {status}")

    @staticmethod
    def handle_subscription_deleted(subscription: Dict, db: Session):
        """Handle subscription cancellation"""
        subscription_id = subscription['id']

        print(f"Subscription deleted: {subscription_id}")

    @staticmethod
    def handle_payment_succeeded(invoice: Dict, db: Session):
        """Handle successful payment"""
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')
        amount_paid = invoice.get('amount_paid', 0) / 100

        print(f"Payment succeeded: ${amount_paid} for subscription {subscription_id}")

    @staticmethod
    def handle_payment_failed(invoice: Dict, db: Session):
        """Handle failed payment"""
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')

        print(f"Payment failed for subscription {subscription_id}")
