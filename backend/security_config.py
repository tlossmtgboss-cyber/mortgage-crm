"""
Security Configuration

Centralized security settings for the mortgage CRM.
This file consolidates all security-related configuration to make
auditing and compliance reporting easier.
"""

import os
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class SecurityConfig:
    """
    Central security configuration for the application.

    All security-related settings should be defined here for:
    - Easy auditing
    - Consistent configuration across modules
    - Compliance documentation
    """

    # ==========================================================================
    # ENVIRONMENT
    # ==========================================================================
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    is_production: bool = field(default_factory=lambda: os.getenv("ENVIRONMENT") == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT")))

    # ==========================================================================
    # AUTHENTICATION
    # ==========================================================================
    # JWT Settings
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Password hashing
    password_hash_schemes: List[str] = field(default_factory=lambda: ["bcrypt"])
    password_min_length: int = 12
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True

    # ==========================================================================
    # COOKIES
    # ==========================================================================
    cookie_secure: bool = field(default_factory=lambda: os.getenv("ENVIRONMENT") == "production")
    cookie_httponly: bool = True
    cookie_samesite: str = "Lax"

    # ==========================================================================
    # CSRF
    # ==========================================================================
    csrf_enabled: bool = True
    csrf_token_length: int = 32
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_exempt_paths: Set[str] = field(default_factory=lambda: {
        "/api/v1/webhook",
        "/api/v1/webhooks",
        "/api/v1/zapier",
        "/api/v1/borrower",
        "/api/v1/csrf-token",
        "/health",
        "/docs",
    })

    # ==========================================================================
    # CORS
    # ==========================================================================
    cors_allowed_methods: List[str] = field(default_factory=lambda: [
        "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"
    ])
    cors_allowed_headers: List[str] = field(default_factory=lambda: [
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Language",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-CSRF-Token",
        "X-Request-ID",
        "X-Visitor-ID",
    ])
    cors_expose_headers: List[str] = field(default_factory=lambda: [
        "Content-Length",
        "Content-Type",
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ])
    cors_max_age: int = 3600

    # ==========================================================================
    # RATE LIMITING
    # ==========================================================================
    rate_limit_enabled: bool = True
    rate_limit_default: int = 100  # requests per minute
    rate_limit_auth: int = 10  # login attempts per hour
    rate_limit_api: int = 1000  # API calls per minute

    # ==========================================================================
    # ENCRYPTION
    # ==========================================================================
    encryption_algorithm: str = "Fernet"  # Consider upgrading to AES-256-GCM
    pii_fields_requiring_encryption: List[str] = field(default_factory=lambda: [
        "ssn",
        "ssn_last_4",
        "credit_score",
        "bank_account_number",
        "routing_number",
        "annual_income",
        "monthly_income",
        "tax_return_data",
    ])

    # ==========================================================================
    # AUDIT LOGGING
    # ==========================================================================
    audit_logging_enabled: bool = True
    audit_log_pii_access: bool = True
    audit_log_retention_days: int = 2555  # ~7 years for GLBA compliance

    # ==========================================================================
    # SECURITY HEADERS
    # ==========================================================================
    security_headers: dict = field(default_factory=lambda: {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        # CSP — no unsafe-eval or unsafe-inline in script-src
        "Content-Security-Policy": "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https:; connect-src 'self' https://api.perenniaai.com https://api.openai.com https://api.anthropic.com https://graph.microsoft.com; frame-ancestors 'none'",
    })

    # ==========================================================================
    # SESSION
    # ==========================================================================
    session_max_concurrent: int = 5  # Max concurrent sessions per user
    session_idle_timeout_minutes: int = 30
    session_absolute_timeout_hours: int = 24

    # ==========================================================================
    # IP FILTERING
    # ==========================================================================
    ip_whitelist_enabled: bool = field(default_factory=lambda: os.getenv("ENVIRONMENT") == "production")
    ip_rate_limit_block_threshold: int = 100  # Block IP after this many failed attempts
    ip_block_duration_minutes: int = 60

    def validate(self) -> List[str]:
        """
        Validate security configuration and return list of warnings/errors.

        Call this at startup to ensure configuration is secure.
        """
        issues = []

        if self.is_production:
            # Production-only checks
            if not os.getenv("SECRET_KEY"):
                issues.append("CRITICAL: SECRET_KEY not set in production")

            if not os.getenv("DATA_ENCRYPTION_KEY"):
                issues.append("CRITICAL: DATA_ENCRYPTION_KEY not set in production, falling back to SECRET_KEY (set a dedicated Fernet key)")

            if self.access_token_expire_minutes > 30:
                issues.append(f"WARNING: Access token expiry ({self.access_token_expire_minutes} min) is longer than recommended (30 min)")

            if not self.csrf_enabled:
                issues.append("CRITICAL: CSRF protection disabled in production")

            if not self.cookie_secure:
                issues.append("CRITICAL: Secure cookies disabled in production")

            if not self.audit_logging_enabled:
                issues.append("WARNING: Audit logging disabled in production")

        return issues


# Global security configuration instance
security_config = SecurityConfig()


def get_security_config() -> SecurityConfig:
    """Get the security configuration instance."""
    return security_config


def validate_security_config() -> List[str]:
    """
    Validate security configuration at startup.

    Returns list of issues found. Empty list means all checks passed.
    """
    return security_config.validate()
