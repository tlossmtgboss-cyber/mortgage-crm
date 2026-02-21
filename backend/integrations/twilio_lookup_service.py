"""
Twilio Lookup API Integration Service

Provides phone number intelligence for spam filtering:
- Line Type Intelligence (mobile, landline, voip)
- Carrier Information
- Caller Name (CNAM)
- Spam score calculation from indicators

Cost: ~$0.01-0.05 per lookup depending on fields requested
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)

# Try to import Twilio client
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TwilioClient = None
    TWILIO_AVAILABLE = False
    logger.warning("Twilio SDK not available - phone lookup disabled")


@dataclass
class LookupResult:
    """Result from Twilio Lookup API"""
    phone_number: str
    valid: bool
    carrier_name: Optional[str] = None
    carrier_type: Optional[str] = None  # wireless, landline, voip
    line_type: Optional[str] = None  # mobile, landline, fixedVoip, nonFixedVoip
    caller_name: Optional[str] = None
    caller_type: Optional[str] = None  # CONSUMER, BUSINESS
    country_code: Optional[str] = None
    spam_score: int = 0  # 0-100, higher = more likely spam
    risk_level: str = "low"  # low, medium, high
    raw_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TwilioLookupService:
    """
    Twilio Lookup API v2 integration for phone number intelligence.

    Features:
    - Line Type Intelligence (~$0.01/lookup)
    - Caller Name (CNAM) (~$0.01/lookup)
    - Carrier Information (included)

    Spam Score Calculation:
    - VOIP numbers from certain carriers: +30 points
    - No caller name (CNAM): +20 points
    - Non-fixed VOIP: +25 points
    - International with no CNAM: +15 points
    - Known spam carrier patterns: +40 points
    """

    # Known high-risk VOIP carriers often used for spam
    HIGH_RISK_CARRIERS = [
        "bandwidth.com", "telnyx", "plivo", "vonage api",
        "twilio", "signalwire", "flowroute"
    ]

    # Carriers that are generally legitimate
    TRUSTED_CARRIERS = [
        "verizon", "at&t", "t-mobile", "sprint",
        "us cellular", "cricket", "metro"
    ]

    def __init__(self):
        self.account_sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        self.auth_token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        self.enabled = bool(
            TWILIO_AVAILABLE and
            self.account_sid and
            self.auth_token and
            os.getenv("TWILIO_LOOKUP_ENABLED", "true").lower() == "true"
        )

        if self.enabled:
            self.client = TwilioClient(self.account_sid, self.auth_token)
            logger.info("Twilio Lookup Service initialized")
        else:
            self.client = None
            logger.info("Twilio Lookup Service disabled")

    async def lookup_phone(
        self,
        phone_number: str,
        include_caller_name: bool = True,
        include_line_type: bool = True
    ) -> LookupResult:
        """
        Perform Twilio Lookup API call for phone intelligence.

        Args:
            phone_number: Phone number in E.164 format (e.g., +14155551234)
            include_caller_name: Include CNAM lookup (~$0.01 extra)
            include_line_type: Include line type intelligence (~$0.01 extra)

        Returns:
            LookupResult with phone intelligence data
        """
        if not self.enabled:
            return LookupResult(
                phone_number=phone_number,
                valid=True,
                spam_score=0,
                risk_level="unknown",
                error="Lookup service disabled"
            )

        try:
            # Build fields list
            fields = ["carrier"]  # Always included, no extra cost
            if include_line_type:
                fields.append("line_type_intelligence")
            if include_caller_name:
                fields.append("caller_name")

            # Perform lookup (sync call, but typically fast)
            lookup = self.client.lookups.v2.phone_numbers(phone_number).fetch(
                fields=",".join(fields)
            )

            # Extract data
            carrier_info = lookup.carrier or {}
            line_type_info = lookup.line_type_intelligence or {}
            caller_name_info = lookup.caller_name or {}

            # Build result
            result = LookupResult(
                phone_number=lookup.phone_number,
                valid=lookup.valid,
                carrier_name=carrier_info.get("name"),
                carrier_type=carrier_info.get("type"),
                line_type=line_type_info.get("type"),
                caller_name=caller_name_info.get("caller_name"),
                caller_type=caller_name_info.get("caller_type"),
                country_code=lookup.country_code,
                raw_data={
                    "carrier": carrier_info,
                    "line_type_intelligence": line_type_info,
                    "caller_name": caller_name_info,
                    "national_format": lookup.national_format,
                    "url": lookup.url
                }
            )

            # Calculate spam score
            result.spam_score = self._calculate_spam_score(result)
            result.risk_level = self._get_risk_level(result.spam_score)

            logger.info(
                f"Lookup complete for {phone_number}: "
                f"carrier={result.carrier_name}, type={result.line_type}, "
                f"spam_score={result.spam_score}, risk={result.risk_level}"
            )

            return result

        except Exception as e:
            logger.error(f"Twilio Lookup failed for {mask_phone(phone_number)}: {e}")
            return LookupResult(
                phone_number=phone_number,
                valid=False,
                spam_score=50,  # Unknown = moderate risk
                risk_level="medium",
                error=str(e)
            )

    def _calculate_spam_score(self, result: LookupResult) -> int:
        """
        Calculate spam score 0-100 based on lookup indicators.

        Higher score = more likely to be spam.
        """
        score = 0

        # Check line type
        if result.line_type:
            line_type_lower = result.line_type.lower()
            if "nonfixedvoip" in line_type_lower or "non-fixed" in line_type_lower:
                score += 25  # Non-fixed VOIP often used for spam
            elif "voip" in line_type_lower or "fixedvoip" in line_type_lower:
                score += 15  # Fixed VOIP less risky but still elevated
            elif "landline" in line_type_lower:
                score -= 5  # Landlines rarely spam
            elif "mobile" in line_type_lower:
                score -= 5  # Mobile slightly less risky

        # Check carrier
        if result.carrier_name:
            carrier_lower = result.carrier_name.lower()

            # High-risk carriers
            for high_risk in self.HIGH_RISK_CARRIERS:
                if high_risk in carrier_lower:
                    score += 30
                    break

            # Trusted carriers
            for trusted in self.TRUSTED_CARRIERS:
                if trusted in carrier_lower:
                    score -= 10
                    break

        # Check caller name (CNAM)
        if not result.caller_name:
            score += 20  # No CNAM is suspicious
        elif result.caller_name.upper() in ["WIRELESS CALLER", "CELL PHONE", "UNKNOWN"]:
            score += 10  # Generic names are slightly suspicious

        # International numbers without CNAM
        if result.country_code and result.country_code != "US":
            if not result.caller_name:
                score += 15

        # Ensure score is in valid range
        return max(0, min(100, score))

    def _get_risk_level(self, spam_score: int) -> str:
        """Convert spam score to risk level."""
        if spam_score >= 60:
            return "high"
        elif spam_score >= 30:
            return "medium"
        else:
            return "low"

    def is_enabled(self) -> bool:
        """Check if lookup service is enabled."""
        return self.enabled


# Global instance
twilio_lookup_service = TwilioLookupService()
