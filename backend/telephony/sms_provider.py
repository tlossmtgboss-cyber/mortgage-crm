"""
SMS Provider Abstraction — Primary/Fallback routing for outbound SMS.

Eliminates the Telnyx single-point-of-failure by defining a provider
interface and an ``SMSRouter`` that tries the primary provider first,
then falls back to a secondary on failure.

**Not wired into the existing send path yet.**  To activate:

    1. Set ``SMS_FALLBACK_ENABLED=true`` in env.
    2. Ensure Twilio credentials are present:
       ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN``, ``TWILIO_SMS_FROM_NUMBER``
    3. Wire ``get_sms_router().send_sms(...)`` into the chokepoint
       (``telephony/sms.py``).

Config env vars
---------------
- ``SMS_PRIMARY_PROVIDER``   — ``telnyx`` (default) or ``twilio``
- ``SMS_FALLBACK_PROVIDER``  — ``twilio`` (default) or ``telnyx``
- ``SMS_FALLBACK_ENABLED``   — ``false`` (default).  Set ``true`` to enable.
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SMSResult:
    """Outcome of an SMS send attempt."""
    success: bool
    message_id: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None
    fallback_used: bool = False


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SMSProvider(ABC):
    """Protocol that every SMS provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. ``'telnyx'`` or ``'twilio'``."""
        ...

    @abstractmethod
    def send_sms(
        self,
        *,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> SMSResult:
        """Send a single SMS/MMS synchronously.

        Parameters
        ----------
        to : str
            Destination phone in E.164 format.
        body : str
            Message text.
        from_number : str, optional
            Sender phone (E.164).  Provider implementations should fall
            back to their own default if not supplied.
        media_urls : list[str], optional
            Public media URLs for MMS.

        Returns
        -------
        SMSResult
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has enough credentials to operate."""
        ...


# ---------------------------------------------------------------------------
# Telnyx implementation
# ---------------------------------------------------------------------------

class TelnyxSMSProvider(SMSProvider):
    """Wraps the existing Telnyx SMS path (``telephony.sms._send_sms_raw``)."""

    @property
    def name(self) -> str:
        return "telnyx"

    def is_configured(self) -> bool:
        return bool(os.getenv("TELNYX_API_KEY", "").strip())

    def send_sms(
        self,
        *,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> SMSResult:
        from_number = from_number or os.getenv(
            "TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""),
        )
        messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "") or None

        try:
            # Re-use the existing raw send to avoid duplicating SDK init logic
            from telephony.sms import _send_sms_raw

            result = _send_sms_raw(
                to=to,
                from_=from_number,
                text=body,
                messaging_profile_id=messaging_profile_id,
                media_urls=media_urls,
            )
            return SMSResult(
                success=True,
                message_id=result.get("id"),
                provider=self.name,
            )
        except Exception as exc:
            logger.error("TelnyxSMSProvider.send_sms failed: %s", exc)
            return SMSResult(
                success=False,
                provider=self.name,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Twilio implementation
# ---------------------------------------------------------------------------

_twilio_client = None
_twilio_lock = threading.Lock()


def _get_twilio_client():
    """Lazy-init a Twilio REST client."""
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not account_sid or not auth_token:
        return None

    with _twilio_lock:
        if _twilio_client is not None:
            return _twilio_client
        try:
            from twilio.rest import Client
            _twilio_client = Client(account_sid, auth_token)
            logger.info("Twilio SMS client initialized (fallback provider)")
            return _twilio_client
        except Exception:
            logger.exception("Failed to initialise Twilio client")
            return None


class TwilioSMSProvider(SMSProvider):
    """Twilio SMS fallback provider.

    Env vars
    --------
    - ``TWILIO_ACCOUNT_SID``
    - ``TWILIO_AUTH_TOKEN``
    - ``TWILIO_SMS_FROM_NUMBER`` — the Twilio number to send from
    """

    @property
    def name(self) -> str:
        return "twilio"

    def is_configured(self) -> bool:
        return bool(
            os.getenv("TWILIO_ACCOUNT_SID", "").strip()
            and os.getenv("TWILIO_AUTH_TOKEN", "").strip()
            and os.getenv("TWILIO_SMS_FROM_NUMBER", "").strip()
        )

    def send_sms(
        self,
        *,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> SMSResult:
        from_number = from_number or os.getenv("TWILIO_SMS_FROM_NUMBER", "")
        if not from_number:
            return SMSResult(
                success=False,
                provider=self.name,
                error="TWILIO_SMS_FROM_NUMBER not configured",
            )

        client = _get_twilio_client()
        if client is None:
            return SMSResult(
                success=False,
                provider=self.name,
                error="Twilio client not available — check TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN",
            )

        try:
            kwargs: Dict[str, Any] = {
                "to": to,
                "from_": from_number,
                "body": body,
            }
            if media_urls:
                kwargs["media_url"] = media_urls

            message = client.messages.create(**kwargs)

            return SMSResult(
                success=True,
                message_id=message.sid,
                provider=self.name,
            )
        except Exception as exc:
            logger.error("TwilioSMSProvider.send_sms failed: %s", exc)
            return SMSResult(
                success=False,
                provider=self.name,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS: Dict[str, type] = {
    "telnyx": TelnyxSMSProvider,
    "twilio": TwilioSMSProvider,
}


def _build_provider(name: str) -> SMSProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown SMS provider: {name!r}. Valid: {list(_PROVIDERS)}")
    return cls()


# ---------------------------------------------------------------------------
# Router — tries primary, falls back to secondary
# ---------------------------------------------------------------------------

class SMSRouter:
    """Routes SMS through a primary provider with optional fallback.

    Usage::

        router = SMSRouter()          # reads env vars
        result = router.send_sms(to="+1...", body="Hello")

    The router does **not** run compliance checks — that responsibility
    stays with the existing chokepoint in ``telephony/sms.py``.
    """

    def __init__(
        self,
        primary: Optional[SMSProvider] = None,
        fallback: Optional[SMSProvider] = None,
        fallback_enabled: Optional[bool] = None,
    ):
        primary_name = os.getenv("SMS_PRIMARY_PROVIDER", "telnyx").lower().strip()
        fallback_name = os.getenv("SMS_FALLBACK_PROVIDER", "twilio").lower().strip()

        self.primary = primary or _build_provider(primary_name)
        self.fallback = fallback or _build_provider(fallback_name)

        if fallback_enabled is not None:
            self.fallback_enabled = fallback_enabled
        else:
            self.fallback_enabled = os.getenv(
                "SMS_FALLBACK_ENABLED", "false",
            ).lower().strip() in ("true", "1", "yes")

    def send_sms(
        self,
        *,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> SMSResult:
        """Attempt primary provider; fall back to secondary on failure."""
        result = self.primary.send_sms(
            to=to, body=body, from_number=from_number, media_urls=media_urls,
        )
        if result.success:
            return result

        # Primary failed — try fallback if enabled and configured
        if not self.fallback_enabled:
            logger.warning(
                "SMS primary (%s) failed and fallback is disabled. Error: %s",
                self.primary.name, result.error,
            )
            return result

        if not self.fallback.is_configured():
            logger.error(
                "SMS primary (%s) failed and fallback (%s) is not configured. "
                "Error: %s",
                self.primary.name, self.fallback.name, result.error,
            )
            return result

        logger.warning(
            "SMS primary (%s) failed (%s) — attempting fallback (%s)",
            self.primary.name, result.error, self.fallback.name,
        )

        fallback_result = self.fallback.send_sms(
            to=to, body=body, from_number=None,  # use fallback's own from-number
            media_urls=media_urls,
        )
        fallback_result.fallback_used = True

        if fallback_result.success:
            logger.info(
                "SMS fallback (%s) succeeded for ...%s",
                self.fallback.name, to[-4:],
            )
        else:
            logger.error(
                "SMS fallback (%s) also failed for ...%s: %s",
                self.fallback.name, to[-4:], fallback_result.error,
            )

        return fallback_result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router_instance: Optional[SMSRouter] = None
_router_lock = threading.Lock()


def get_sms_router() -> SMSRouter:
    """Return the module-level SMSRouter singleton."""
    global _router_instance
    if _router_instance is not None:
        return _router_instance
    with _router_lock:
        if _router_instance is None:
            _router_instance = SMSRouter()
        return _router_instance


def reset_sms_router() -> None:
    """Reset the singleton (for testing or hot-reload)."""
    global _router_instance
    _router_instance = None
