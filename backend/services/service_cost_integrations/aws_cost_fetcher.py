"""
AWS cost fetcher - fetches S3 storage and other AWS costs.
"""

from datetime import date, timedelta
from decimal import Decimal
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class AWSCostFetcher(BaseCostFetcher):
    """Fetches AWS (primarily S3) costs."""

    provider_type = "aws_s3"
    unit_type = "gb"

    # S3 Standard pricing (US East)
    COST_PER_GB = Decimal("0.023")
    COST_PER_1000_REQUESTS = Decimal("0.0004")

    def __init__(self, api_key: str = None, secret_key: str = None, region: str = None):
        super().__init__(api_key or os.getenv("AWS_ACCESS_KEY_ID"))
        self.secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

    def validate_credentials(self) -> bool:
        return bool(self.api_key and self.secret_key)

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """Fetch AWS costs for the period using Cost Explorer."""
        if not self.validate_credentials():
            return FetchResult.error_result("AWS credentials not configured")

        self.log_fetch_start(start_date, end_date)

        try:
            import boto3

            client = boto3.client(
                'ce',
                aws_access_key_id=self.api_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            response = client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                Filter={
                    'Dimensions': {
                        'Key': 'SERVICE',
                        'Values': ['Amazon Simple Storage Service']
                    }
                }
            )

            records = []

            for result in response.get('ResultsByTime', []):
                usage_date = date.fromisoformat(result['TimePeriod']['Start'])
                cost = Decimal(result['Total']['UnblendedCost']['Amount'])

                if cost > 0:
                    records.append(UsageRecord(
                        usage_date=usage_date,
                        usage_type="storage",
                        quantity=cost / self.COST_PER_GB,  # Estimate GB from cost
                        unit_type="gb",
                        unit_cost=self.COST_PER_GB,
                        total_cost=cost,
                        metadata={
                            "service": "Amazon S3",
                            "currency": result['Total']['UnblendedCost']['Unit']
                        }
                    ))

            self.log_fetch_complete(len(records))
            return FetchResult.success_result(records, raw_response=response)

        except ImportError:
            return FetchResult.error_result("boto3 package not installed")
        except Exception as e:
            self.log_fetch_error(str(e))
            return FetchResult.error_result(str(e))

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate S3 storage cost."""
        storage_class = kwargs.get("storage_class", "standard")

        # Different rates for different storage classes
        rates = {
            "standard": Decimal("0.023"),
            "intelligent_tiering": Decimal("0.023"),
            "standard_ia": Decimal("0.0125"),
            "glacier": Decimal("0.004"),
            "glacier_deep_archive": Decimal("0.00099"),
        }

        rate = rates.get(storage_class, self.COST_PER_GB)
        return quantity * rate
