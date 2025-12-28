"""
Stripe cost fetcher - fetches payment processing fees.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class StripeCostFetcher(BaseCostFetcher):
    """Fetches Stripe payment processing fees."""

    provider_type = "stripe"
    unit_type = "transaction"

    # Stripe's standard rates (US)
    BASE_RATE = Decimal("0.029")  # 2.9%
    PER_TRANSACTION = Decimal("0.30")  # $0.30 per transaction

    def __init__(self, api_key: str = None):
        super().__init__(api_key or os.getenv("STRIPE_SECRET_KEY"))

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """Fetch Stripe transaction fees for the period."""
        if not self.validate_credentials():
            return FetchResult.error_result("Stripe API key not configured")

        self.log_fetch_start(start_date, end_date)

        try:
            import stripe
            stripe.api_key = self.api_key

            # Convert dates to timestamps
            start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
            end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())

            # Fetch balance transactions (fees)
            transactions = stripe.BalanceTransaction.list(
                created={"gte": start_ts, "lte": end_ts},
                type="charge",
                limit=100
            )

            records = []
            for txn in transactions.auto_paging_iter():
                # Stripe returns amounts in cents
                amount = Decimal(str(txn.amount)) / 100
                fee = Decimal(str(txn.fee)) / 100

                record = UsageRecord(
                    usage_date=datetime.fromtimestamp(txn.created).date(),
                    usage_type="payment_processing",
                    quantity=Decimal("1"),
                    unit_type="transaction",
                    unit_cost=fee,
                    total_cost=fee,
                    metadata={
                        "transaction_amount": float(amount),
                        "currency": txn.currency,
                        "description": txn.description,
                    },
                    external_id=txn.id
                )
                records.append(record)

            self.log_fetch_complete(len(records))
            return FetchResult.success_result(records)

        except ImportError:
            return FetchResult.error_result("stripe package not installed")
        except Exception as e:
            self.log_fetch_error(str(e))
            return FetchResult.error_result(str(e))

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate Stripe fee for a transaction amount."""
        transaction_amount = kwargs.get("transaction_amount", Decimal("0"))
        percentage_fee = transaction_amount * self.BASE_RATE
        return percentage_fee + self.PER_TRANSACTION
