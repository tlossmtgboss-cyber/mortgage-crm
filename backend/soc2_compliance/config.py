"""
SOC 2 Type II Compliance — Configuration
"""
import os
from dataclasses import dataclass, field
from typing import Set


@dataclass
class SOC2Config:
    """Central configuration for SOC 2 compliance controls."""

    # Encryption
    field_encryption_key: str = ""

    # Session & Authentication
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30
    require_mfa: bool = True
    password_min_length: int = 12
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    password_expiry_days: int = 90
    password_history_count: int = 12  # Cannot reuse last N passwords

    # Audit
    audit_retention_days: int = 730  # 2 years
    audit_log_request_body: bool = False  # Enable cautiously — exclude PII
    audit_log_response_body: bool = False

    # Rate Limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 100
    rate_limit_login_per_minute: int = 10

    # PII Fields to track/encrypt
    pii_fields: Set[str] = field(default_factory=lambda: {
        "ssn", "tax_id", "bank_account", "routing_number",
        "dob", "income", "credit_score"
    })

    # Data Retention
    default_retention_days: int = 730

    # Security Headers
    hsts_max_age: int = 31536000  # 1 year
    content_security_policy: str = "default-src 'self'"

    @classmethod
    def from_env(cls) -> "SOC2Config":
        """Load configuration from environment variables."""
        pii_fields_str = os.getenv("SOC2_PII_FIELDS", "")
        pii_fields = (
            set(pii_fields_str.split(",")) if pii_fields_str
            else cls.__dataclass_fields__["pii_fields"].default_factory()
        )

        return cls(
            field_encryption_key=os.getenv("SOC2_FIELD_ENCRYPTION_KEY", ""),
            session_timeout_minutes=int(os.getenv("SOC2_SESSION_TIMEOUT_MINUTES", "30")),
            max_login_attempts=int(os.getenv("SOC2_MAX_LOGIN_ATTEMPTS", "5")),
            lockout_duration_minutes=int(os.getenv("SOC2_LOCKOUT_DURATION_MINUTES", "30")),
            require_mfa=os.getenv("SOC2_REQUIRE_MFA", "true").lower() == "true",
            password_min_length=int(os.getenv("SOC2_PASSWORD_MIN_LENGTH", "12")),
            password_require_uppercase=os.getenv("SOC2_PASSWORD_REQUIRE_UPPERCASE", "true").lower() == "true",
            password_require_lowercase=os.getenv("SOC2_PASSWORD_REQUIRE_LOWERCASE", "true").lower() == "true",
            password_require_digit=os.getenv("SOC2_PASSWORD_REQUIRE_DIGIT", "true").lower() == "true",
            password_require_special=os.getenv("SOC2_PASSWORD_REQUIRE_SPECIAL", "true").lower() == "true",
            password_expiry_days=int(os.getenv("SOC2_PASSWORD_EXPIRY_DAYS", "90")),
            password_history_count=int(os.getenv("SOC2_PASSWORD_HISTORY_COUNT", "12")),
            audit_retention_days=int(os.getenv("SOC2_AUDIT_RETENTION_DAYS", "730")),
            audit_log_request_body=os.getenv("SOC2_AUDIT_LOG_REQUEST_BODY", "false").lower() == "true",
            audit_log_response_body=os.getenv("SOC2_AUDIT_LOG_RESPONSE_BODY", "false").lower() == "true",
            rate_limit_requests_per_minute=int(os.getenv("SOC2_RATE_LIMIT_RPM", "60")),
            rate_limit_burst=int(os.getenv("SOC2_RATE_LIMIT_BURST", "100")),
            rate_limit_login_per_minute=int(os.getenv("SOC2_RATE_LIMIT_LOGIN_RPM", "10")),
            pii_fields=pii_fields,
            default_retention_days=int(os.getenv("SOC2_DEFAULT_RETENTION_DAYS", "730")),
            hsts_max_age=int(os.getenv("SOC2_HSTS_MAX_AGE", "31536000")),
            content_security_policy=os.getenv("SOC2_CONTENT_SECURITY_POLICY", "default-src 'self'"),
        )
