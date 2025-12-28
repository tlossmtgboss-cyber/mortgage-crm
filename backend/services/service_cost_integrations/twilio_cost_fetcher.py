"""
Twilio cost fetcher - fetches SMS and voice usage.
"""

from datetime import date, datetime
from decimal import Decimal
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class TwilioCostFetcher(BaseCostFetcher):
    """Fetches Twilio SMS and voice usage."""

    provider_type = "twilio"
    unit_type = "message"

    # Standard US pricing
    SMS_COST = Decimal("0.0079")  # Per SMS segment
    VOICE_COST_PER_MIN = Decimal("0.013")  # Per minute outbound

    def __init__(self, api_key: str = None, account_sid: str = None):
        super().__init__(api_key or os.getenv("TWILIO_AUTH_TOKEN"))
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")

    def validate_credentials(self) -> bool:
        return bool(self.api_key and self.account_sid)

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """Fetch Twilio usage for the period."""
        if not self.validate_credentials():
            return FetchResult.error_result("Twilio credentials not configured")

        self.log_fetch_start(start_date, end_date)

        try:
            from twilio.rest import Client

            client = Client(self.account_sid, self.api_key)

            records = []

            # Fetch SMS messages
            messages = client.messages.list(
                date_sent_after=datetime.combine(start_date, datetime.min.time()),
                date_sent_before=datetime.combine(end_date, datetime.max.time()),
            )

            # Group by date
            sms_by_date = {}
            for msg in messages:
                msg_date = msg.date_sent.date() if msg.date_sent else start_date
                if msg_date not in sms_by_date:
                    sms_by_date[msg_date] = {"count": 0, "segments": 0}
                sms_by_date[msg_date]["count"] += 1
                sms_by_date[msg_date]["segments"] += msg.num_segments or 1

            for usage_date, data in sms_by_date.items():
                total_cost = Decimal(str(data["segments"])) * self.SMS_COST
                records.append(UsageRecord(
                    usage_date=usage_date,
                    usage_type="sms",
                    quantity=Decimal(str(data["count"])),
                    unit_type="message",
                    unit_cost=self.SMS_COST,
                    total_cost=total_cost,
                    metadata={"segments": data["segments"]}
                ))

            # Fetch voice calls
            calls = client.calls.list(
                start_time_after=datetime.combine(start_date, datetime.min.time()),
                start_time_before=datetime.combine(end_date, datetime.max.time()),
            )

            # Group by date
            calls_by_date = {}
            for call in calls:
                call_date = call.start_time.date() if call.start_time else start_date
                if call_date not in calls_by_date:
                    calls_by_date[call_date] = {"count": 0, "minutes": 0}
                calls_by_date[call_date]["count"] += 1
                duration = int(call.duration or 0)
                calls_by_date[call_date]["minutes"] += (duration + 59) // 60  # Round up

            for usage_date, data in calls_by_date.items():
                total_cost = Decimal(str(data["minutes"])) * self.VOICE_COST_PER_MIN
                records.append(UsageRecord(
                    usage_date=usage_date,
                    usage_type="voice",
                    quantity=Decimal(str(data["count"])),
                    unit_type="call",
                    unit_cost=self.VOICE_COST_PER_MIN,
                    total_cost=total_cost,
                    metadata={"minutes": data["minutes"]}
                ))

            self.log_fetch_complete(len(records))
            return FetchResult.success_result(records)

        except ImportError:
            return FetchResult.error_result("twilio package not installed")
        except Exception as e:
            self.log_fetch_error(str(e))
            return FetchResult.error_result(str(e))

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate cost for SMS or voice usage."""
        usage_type = kwargs.get("usage_type", "sms")

        if usage_type == "sms":
            segments = kwargs.get("segments", 1)
            return Decimal(str(segments)) * self.SMS_COST
        elif usage_type == "voice":
            minutes = kwargs.get("minutes", 1)
            return Decimal(str(minutes)) * self.VOICE_COST_PER_MIN

        return Decimal("0")
