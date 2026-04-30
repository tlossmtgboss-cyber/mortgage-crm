"""
Perennia iMessage integration — configuration.

Reads from environment via Pydantic Settings. Slot into your existing
`app/core/config.py` Settings class as a nested field, or import directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IMessageSettings(BaseSettings):
    """Settings for the BlueBubbles-backed iMessage channel."""

    model_config = SettingsConfigDict(
        env_prefix="IMESSAGE_",
        env_file=".env",
        extra="ignore",
    )

    # ---- BlueBubbles server ------------------------------------------------
    bb_base_url: str = Field(
        ...,
        description="Cloudflare Tunnel hostname, e.g. https://imessage-1.tldevelopment.dev",
    )
    bb_password: str = Field(..., description="BlueBubbles server password")

    # Cloudflare Access service-token headers (defense-in-depth in front of
    # the Mac). Optional — only required if the tunnel sits behind an Access
    # policy (recommended).
    cf_access_client_id: Optional[str] = None
    cf_access_client_secret: Optional[str] = None

    # ---- Webhook security --------------------------------------------------
    # BlueBubbles does not sign webhooks. We protect the endpoint with an
    # opaque token in the URL path that only the Mac knows. Rotate per deploy.
    webhook_url_secret: str = Field(...)

    # ---- Telnyx fallback ---------------------------------------------------
    # When the iMessage lookup says SMS, or when iMessage delivery errors,
    # we hand off to your existing Telnyx integration.
    telnyx_fallback_enabled: bool = True

    # ---- Behavior tuning ---------------------------------------------------
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    retry_backoff_base: float = 0.5

    imessage_lookup_cache_ttl_seconds: int = 60 * 60 * 24 * 7  # 7d
    typing_indicator_dwell_ms: int = 1500

    # Default sender identity on the Mac. For a single-line deployment this
    # is the email or phone tied to the Mac's Apple ID. For multi-line, look
    # up the line via tenant routing instead and ignore this default.
    default_sender_handle: str = Field(
        ..., description="e.g. '+18649820355' or '[email protected]'"
    )

    # ---- Brand / vCard for contact-card sends -----------------------------
    brand_name: str = "TL Mortgage"
    brand_vcard_cdn_url: Optional[str] = None  # https URL ending in .vcf


@lru_cache(maxsize=1)
def get_imessage_settings() -> IMessageSettings:
    return IMessageSettings()  # type: ignore[call-arg]
