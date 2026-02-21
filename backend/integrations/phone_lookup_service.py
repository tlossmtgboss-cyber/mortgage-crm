"""
Provider-Agnostic Phone Lookup Service

Supports both Twilio and Telnyx for phone number intelligence:
- Line Type Intelligence (mobile, landline, voip)
- Carrier Information
- Caller Name (CNAM) - Twilio only
- Spam score calculation from indicators

Provider selected via TELEPHONY_PROVIDER environment variable.
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Determine which provider to use
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "twilio").lower()


@dataclass
class LookupResult:
    """Result from phone lookup API"""
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
    provider: str = "unknown"
    raw_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PhoneLookupProvider(ABC):
    """Abstract base class for phone lookup providers"""

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

    @abstractmethod
    async def lookup_phone(
        self,
        phone_number: str,
        include_caller_name: bool = True,
        include_line_type: bool = True
    ) -> LookupResult:
        """Perform phone number lookup"""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if lookup service is enabled"""
        pass

    def _calculate_spam_score(self, result: LookupResult) -> int:
        """Calculate spam score 0-100 based on lookup indicators."""
        score = 0

        # Check line type
        if result.line_type:
            line_type_lower = result.line_type.lower()
            if "nonfixedvoip" in line_type_lower or "non-fixed" in line_type_lower:
                score += 25
            elif "voip" in line_type_lower or "fixedvoip" in line_type_lower:
                score += 15
            elif "landline" in line_type_lower:
                score -= 5
            elif "mobile" in line_type_lower:
                score -= 5

        # Check carrier
        if result.carrier_name:
            carrier_lower = result.carrier_name.lower()

            for high_risk in self.HIGH_RISK_CARRIERS:
                if high_risk in carrier_lower:
                    score += 30
                    break

            for trusted in self.TRUSTED_CARRIERS:
                if trusted in carrier_lower:
                    score -= 10
                    break

        # Check caller name (CNAM)
        if not result.caller_name:
            score += 20
        elif result.caller_name.upper() in ["WIRELESS CALLER", "CELL PHONE", "UNKNOWN"]:
            score += 10

        # International numbers without CNAM
        if result.country_code and result.country_code != "US":
            if not result.caller_name:
                score += 15

        return max(0, min(100, score))

    def _get_risk_level(self, spam_score: int) -> str:
        """Convert spam score to risk level."""
        if spam_score >= 60:
            return "high"
        elif spam_score >= 30:
            return "medium"
        else:
            return "low"


class TwilioLookupProvider(PhoneLookupProvider):
    """Twilio Lookup API v2 implementation"""

    def __init__(self):
        self.account_sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        self.auth_token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        self.client = None
        self._enabled = False

        try:
            from twilio.rest import Client as TwilioClient
            if self.account_sid and self.auth_token:
                lookup_enabled = os.getenv("TWILIO_LOOKUP_ENABLED", "true").lower() == "true"
                if lookup_enabled:
                    self.client = TwilioClient(self.account_sid, self.auth_token)
                    self._enabled = True
                    logger.info("Twilio Lookup Service initialized")
        except ImportError:
            logger.warning("Twilio SDK not available")

    def is_enabled(self) -> bool:
        return self._enabled

    async def lookup_phone(
        self,
        phone_number: str,
        include_caller_name: bool = True,
        include_line_type: bool = True
    ) -> LookupResult:
        if not self._enabled:
            return LookupResult(
                phone_number=phone_number,
                valid=True,
                spam_score=0,
                risk_level="unknown",
                provider="twilio",
                error="Lookup service disabled"
            )

        try:
            fields = ["carrier"]
            if include_line_type:
                fields.append("line_type_intelligence")
            if include_caller_name:
                fields.append("caller_name")

            lookup = self.client.lookups.v2.phone_numbers(phone_number).fetch(
                fields=",".join(fields)
            )

            carrier_info = lookup.carrier or {}
            line_type_info = lookup.line_type_intelligence or {}
            caller_name_info = lookup.caller_name or {}

            result = LookupResult(
                phone_number=lookup.phone_number,
                valid=lookup.valid,
                carrier_name=carrier_info.get("name"),
                carrier_type=carrier_info.get("type"),
                line_type=line_type_info.get("type"),
                caller_name=caller_name_info.get("caller_name"),
                caller_type=caller_name_info.get("caller_type"),
                country_code=lookup.country_code,
                provider="twilio",
                raw_data={
                    "carrier": carrier_info,
                    "line_type_intelligence": line_type_info,
                    "caller_name": caller_name_info,
                    "national_format": lookup.national_format,
                }
            )

            result.spam_score = self._calculate_spam_score(result)
            result.risk_level = self._get_risk_level(result.spam_score)

            logger.info(
                f"Twilio lookup complete for {phone_number}: "
                f"carrier={result.carrier_name}, type={result.line_type}, "
                f"spam_score={result.spam_score}, risk={result.risk_level}"
            )

            return result

        except Exception as e:
            logger.error(f"Twilio Lookup failed: {type(e).__name__}")
            return LookupResult(
                phone_number=phone_number,
                valid=False,
                spam_score=50,
                risk_level="medium",
                provider="twilio",
                error=str(e)
            )


class TelnyxLookupProvider(PhoneLookupProvider):
    """Telnyx Number Lookup API implementation"""

    def __init__(self):
        self.api_key = os.getenv("TELNYX_API_KEY")
        self.client = None
        self._enabled = False

        try:
            from telnyx import Telnyx
            if self.api_key:
                lookup_enabled = os.getenv("TELNYX_LOOKUP_ENABLED", "true").lower() == "true"
                if lookup_enabled:
                    self.client = Telnyx(api_key=self.api_key)
                    self._enabled = True
                    logger.info("Telnyx Lookup Service initialized")
        except ImportError:
            logger.warning("Telnyx SDK not available")

    def is_enabled(self) -> bool:
        return self._enabled

    async def lookup_phone(
        self,
        phone_number: str,
        include_caller_name: bool = True,
        include_line_type: bool = True
    ) -> LookupResult:
        if not self._enabled:
            return LookupResult(
                phone_number=phone_number,
                valid=True,
                spam_score=0,
                risk_level="unknown",
                provider="telnyx",
                error="Lookup service disabled"
            )

        try:
            # Telnyx Number Lookup API
            # https://developers.telnyx.com/docs/api/v2/number-lookup
            lookup_type = "carrier" if include_line_type else "carrier"

            response = self.client.number_lookups.create(
                phone_number=phone_number,
                type=lookup_type
            )

            data = response.data

            # Extract carrier info
            carrier_info = data.carrier or {}
            portability_info = data.portability or {}

            # Map Telnyx line types to standard format
            line_type_map = {
                "mobile": "mobile",
                "landline": "landline",
                "voip": "fixedVoip",
                "fixed_voip": "fixedVoip",
                "non_fixed_voip": "nonFixedVoip",
                "toll_free": "tollFree",
                "premium_rate": "premiumRate",
            }

            raw_line_type = carrier_info.get("type", "").lower().replace("-", "_")
            mapped_line_type = line_type_map.get(raw_line_type, raw_line_type)

            result = LookupResult(
                phone_number=data.phone_number,
                valid=data.valid_number if hasattr(data, 'valid_number') else True,
                carrier_name=carrier_info.get("name"),
                carrier_type=carrier_info.get("type"),
                line_type=mapped_line_type,
                caller_name=None,  # Telnyx doesn't provide CNAM in basic lookup
                caller_type=None,
                country_code=data.country_code if hasattr(data, 'country_code') else None,
                provider="telnyx",
                raw_data={
                    "carrier": carrier_info,
                    "portability": portability_info,
                    "national_format": data.national_format if hasattr(data, 'national_format') else None,
                }
            )

            result.spam_score = self._calculate_spam_score(result)
            result.risk_level = self._get_risk_level(result.spam_score)

            logger.info(
                f"Telnyx lookup complete for {phone_number}: "
                f"carrier={result.carrier_name}, type={result.line_type}, "
                f"spam_score={result.spam_score}, risk={result.risk_level}"
            )

            return result

        except Exception as e:
            logger.error(f"Telnyx Lookup failed: {type(e).__name__}")
            return LookupResult(
                phone_number=phone_number,
                valid=False,
                spam_score=50,
                risk_level="medium",
                provider="telnyx",
                error=str(e)
            )


class PhoneLookupService:
    """
    Provider-agnostic phone lookup service.

    Automatically uses the configured telephony provider (Twilio or Telnyx).
    """

    def __init__(self):
        self.provider_name = TELEPHONY_PROVIDER

        if self.provider_name == "telnyx":
            self._provider = TelnyxLookupProvider()
        else:
            self._provider = TwilioLookupProvider()

        logger.info(f"Phone Lookup Service initialized with {self.provider_name}")

    async def lookup_phone(
        self,
        phone_number: str,
        include_caller_name: bool = True,
        include_line_type: bool = True
    ) -> LookupResult:
        """
        Perform phone number lookup.

        Args:
            phone_number: Phone number in E.164 format (e.g., +14155551234)
            include_caller_name: Include CNAM lookup (Twilio only, ~$0.01 extra)
            include_line_type: Include line type intelligence (~$0.01 extra)

        Returns:
            LookupResult with phone intelligence data
        """
        return await self._provider.lookup_phone(
            phone_number,
            include_caller_name,
            include_line_type
        )

    def is_enabled(self) -> bool:
        """Check if lookup service is enabled."""
        return self._provider.is_enabled()

    @property
    def provider(self) -> str:
        """Get the current provider name."""
        return self.provider_name


# Global instance - lazy initialization
_lookup_service = None


def get_phone_lookup_service() -> PhoneLookupService:
    """Get or create the global phone lookup service instance"""
    global _lookup_service
    if _lookup_service is None:
        _lookup_service = PhoneLookupService()
    return _lookup_service


# Backwards compatibility alias
phone_lookup_service = None


def _init_lookup_service():
    """Initialize the global phone_lookup_service on first use"""
    global phone_lookup_service
    if phone_lookup_service is None:
        phone_lookup_service = get_phone_lookup_service()
    return phone_lookup_service
