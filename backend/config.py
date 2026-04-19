# backend/config.py - PRODUCTION CONFIGURATION
"""
Perennia AI Configuration Management

Centralized configuration using pydantic-settings for:
- Environment variable validation
- Type coercion
- Default values
- Secret management
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Usage:
        from config import settings
        print(settings.DATABASE_URL)
    """

    # =========================================================================
    # APPLICATION
    # =========================================================================
    ENVIRONMENT: str = Field(default="development", description="Environment name")
    VERSION: str = Field(default="1.0.0", description="Application version")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # =========================================================================
    # DATABASE
    # =========================================================================
    DATABASE_URL: str = Field(
        default="postgresql://localhost:5432/mortgage_crm",
        description="PostgreSQL connection URL"
    )
    DB_POOL_SIZE: int = Field(default=20, description="Connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max overflow connections")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Pool timeout in seconds")

    # =========================================================================
    # REDIS
    # =========================================================================
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Max Redis connections")

    # =========================================================================
    # ANTHROPIC AI
    # =========================================================================
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    ANTHROPIC_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use"
    )
    ANTHROPIC_MAX_TOKENS: int = Field(default=1024, description="Max tokens per response")

    LO_PHONE_NUMBER: str = Field(default="", description="Loan Officer phone number")

    # =========================================================================
    # APPLICATION URLS
    # =========================================================================
    BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Base URL for the application"
    )
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend application URL"
    )
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins"
    )

    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_CHAT_MESSAGES: int = Field(
        default=60,
        description="Max chat messages per minute"
    )
    RATE_LIMIT_SESSION_CREATE: int = Field(
        default=10,
        description="Max session creations per hour"
    )
    RATE_LIMIT_CALLS: int = Field(
        default=3,
        description="Max call initiations per hour"
    )

    # =========================================================================
    # SMART DOCS
    # =========================================================================
    PRESIGNED_URL_EXPIRY_SECONDS: int = Field(
        default=300,
        description="S3 presigned URL expiry in seconds"
    )

    # =========================================================================
    # CIRCUIT BREAKER
    # =========================================================================
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5,
        description="Failures before opening circuit"
    )
    CIRCUIT_BREAKER_TIMEOUT: float = Field(
        default=30.0,
        description="Request timeout in seconds"
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=30,
        description="Seconds before attempting recovery"
    )

    # =========================================================================
    # CACHING
    # =========================================================================
    CACHE_ENABLED: bool = Field(default=True, description="Enable response caching")
    CACHE_DEFAULT_TTL: int = Field(
        default=3600,
        description="Default cache TTL (1 hour)"
    )
    CACHE_LONG_TTL: int = Field(
        default=604800,
        description="Long cache TTL (7 days)"
    )

    # =========================================================================
    # BUSINESS HOURS
    # =========================================================================
    BUSINESS_HOURS_TIMEZONE: str = Field(
        default="America/New_York",
        description="Timezone for business hours"
    )
    BUSINESS_HOURS_START: int = Field(
        default=8,
        description="Business hours start (24h)"
    )
    BUSINESS_HOURS_END: int = Field(
        default=20,
        description="Business hours end (24h)"
    )

    # =========================================================================
    # SALESFORCE INTEGRATION
    # =========================================================================
    SALESFORCE_CLIENT_ID: str = Field(
        default="",
        description="Salesforce Connected App Consumer Key"
    )
    SALESFORCE_CLIENT_SECRET: str = Field(
        default="",
        description="Salesforce Connected App Consumer Secret"
    )
    SALESFORCE_REDIRECT_URI: Optional[str] = Field(
        default=None,
        description="Salesforce OAuth callback URI (defaults to BASE_URL/api/integrations/salesforce/callback)"
    )
    SALESFORCE_SANDBOX: bool = Field(
        default=False,
        description="Use Salesforce sandbox environment"
    )
    SALESFORCE_API_VERSION: str = Field(
        default="v60.0",
        description="Salesforce API version"
    )

    # =========================================================================
    # GOOGLE CLOUD TEXT-TO-SPEECH
    # =========================================================================
    GOOGLE_TTS_ENABLED: bool = Field(
        default=False,
        description="Enable Google Cloud TTS (uses GOOGLE_APPLICATION_CREDENTIALS env var)"
    )
    GOOGLE_TTS_VOICE: str = Field(
        default="en-US-Neural2-C",
        description="Default Google TTS voice name"
    )
    GOOGLE_TTS_LANGUAGE: str = Field(
        default="en-US",
        description="Default Google TTS language code"
    )

    # =========================================================================
    # MONITORING
    # =========================================================================
    SENTRY_DSN: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error tracking"
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format: json or text")

    # =========================================================================
    # SESSION SETTINGS
    # =========================================================================
    SESSION_TIMEOUT_MINUTES: int = Field(
        default=30,
        description="Session timeout in minutes"
    )
    SESSION_MAX_MESSAGES: int = Field(
        default=100,
        description="Max messages per session"
    )

    # =========================================================================
    # QUALITY THRESHOLDS
    # =========================================================================
    QUALITY_ALERT_THRESHOLD: int = Field(
        default=50,
        description="Quality score below which to alert"
    )
    INTENT_HIGH_THRESHOLD: int = Field(
        default=70,
        description="Intent score considered high"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars


# Create singleton instance
settings = Settings()


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def get_database_url() -> str:
    """Get database URL with proper format for SQLAlchemy."""
    url = settings.DATABASE_URL
    # Fix Railway postgres:// format
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def is_production() -> bool:
    """Check if running in production environment."""
    return settings.ENVIRONMENT.lower() in ("production", "prod")


def is_development() -> bool:
    """Check if running in development environment."""
    return settings.ENVIRONMENT.lower() in ("development", "dev", "local")


def get_log_level() -> int:
    """Get numeric log level."""
    import logging
    return getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)


# =========================================================================
# VALIDATION
# =========================================================================

def validate_config():
    """Validate critical configuration on startup."""
    errors = []

    if is_production():
        if not settings.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required in production")

        if settings.DEBUG:
            errors.append("DEBUG should be False in production")

        if "localhost" in settings.BASE_URL:
            errors.append("BASE_URL should not be localhost in production")

        # Redis is required in production for Celery, caching, and rate limiting
        if not settings.REDIS_URL or "localhost" in settings.REDIS_URL:
            errors.append("REDIS_URL must be set to a production Redis instance")

    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")

    return True


# Run validation on import in production
if is_production():
    try:
        validate_config()
    except ValueError as e:
        import logging
        logging.warning(f"Configuration validation: {e}")
