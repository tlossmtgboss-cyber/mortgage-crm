"""
Authentication Configuration

Centralized configuration for JWT and authentication settings.
Uses Pydantic for validation and environment variable loading.

Security Best Practices:
- Use RS256 (asymmetric) in production for better security
- HS256 (symmetric) is acceptable for simple deployments
- Rotate keys every 90 days
- Never commit keys to version control

Usage:
    from auth.config import get_auth_settings

    settings = get_auth_settings()
    print(f"Algorithm: {settings.algorithm}")
    print(f"Token expires in: {settings.access_token_expire_minutes} minutes")
"""

import os
import secrets
import logging
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from functools import lru_cache

logger = logging.getLogger(__name__)


class AuthSettings(BaseModel):
    """Authentication and JWT settings."""

    # JWT Configuration
    secret_key: str = Field(
        default_factory=lambda: os.getenv("SECRET_KEY", ""),
        description="Secret key for JWT signing (HS256)"
    )
    algorithm: Literal["HS256", "RS256"] = Field(
        default_factory=lambda: os.getenv("AUTH_ALGORITHM", "RS256"),
        description="JWT signing algorithm. RS256 (asymmetric) is the default and "
        "required in production. HS256 is allowed only in development/test. "
        "'none' is explicitly rejected to prevent algorithm confusion attacks."
    )
    access_token_expire_minutes: int = Field(
        default=15,
        description="Access token expiration in minutes (reduced from 30 for security)"
    )
    refresh_token_expire_days: int = Field(
        default=1,
        description="Refresh token expiration in days (reduced from 7 to 1 for security — "
        "limits the window for stolen refresh token abuse)"
    )

    # Token claims
    issuer: str = Field(
        default="perennia-ai",
        description="JWT issuer claim (iss)"
    )
    audience: str = Field(
        default="perennia-crm",
        description="JWT audience claim (aud)"
    )

    # RS256 Keys
    private_key_path: Optional[str] = Field(
        default_factory=lambda: os.getenv("AUTH_PRIVATE_KEY_PATH"),
        description="Path to RSA private key for RS256 signing"
    )
    public_key_path: Optional[str] = Field(
        default_factory=lambda: os.getenv("AUTH_PUBLIC_KEY_PATH"),
        description="Path to RSA public key for RS256 verification"
    )

    # Token Blacklist
    redis_url: Optional[str] = Field(
        default_factory=lambda: os.getenv("REDIS_URL"),
        description="Redis URL for token blacklist"
    )
    token_blacklist_enabled: bool = Field(
        default_factory=lambda: os.getenv("AUTH_TOKEN_BLACKLIST_ENABLED", "true").lower() == "true",
        description="Enable token blacklist in Redis. Defaults to TRUE per 2026-04-19 audit H1 — "
        "disabling means stolen/logged-out tokens remain valid for the full access-token TTL "
        "with no revocation path. Set AUTH_TOKEN_BLACKLIST_ENABLED=false to disable temporarily."
    )

    # Security Settings
    require_secure_cookies: bool = Field(
        default=True,
        description="Require secure cookies for refresh tokens"
    )
    same_site_policy: Literal["strict", "lax", "none"] = Field(
        default="lax",
        description="SameSite cookie policy"
    )

    @field_validator("algorithm", mode="after")
    @classmethod
    def reject_hs256_in_production(cls, v):
        """HS256 is forbidden in production — RS256 is mandatory for mortgage data."""
        environment = os.getenv("ENVIRONMENT", "development")
        is_prod = environment.lower() in ("production", "prod") or os.getenv("RAILWAY_ENVIRONMENT")
        if v == "HS256" and is_prod:
            raise ValueError(
                "HS256 is not allowed in production. Set AUTH_ALGORITHM=RS256 and "
                "configure AUTH_PRIVATE_KEY / AUTH_PUBLIC_KEY environment variables."
            )
        return v

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v):
        """Ensure secret key is set in production (for HS256)."""
        environment = os.getenv("ENVIRONMENT", "development")
        algorithm = os.getenv("AUTH_ALGORITHM", "RS256")

        # Secret key only required for HS256
        if algorithm == "RS256":
            return v or "not-used-for-rs256"

        if not v and environment != "development":
            raise ValueError("SECRET_KEY environment variable is required in production")
        if not v:
            logger.warning("SECRET_KEY not set - using generated key for development only")
            return secrets.token_hex(32)
        return v

    class Config:
        env_prefix = "AUTH_"


@lru_cache()
def get_auth_settings() -> AuthSettings:
    """Get cached authentication settings."""
    return AuthSettings()
