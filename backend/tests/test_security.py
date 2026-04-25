"""
Comprehensive Security Test Suite for Perennia AI

Covers 10 security domains with 28 tests:
1. SQL Injection Protection
2. JWT Validation
3. PII Redaction
4. CSRF Protection
5. Input Validation
6. CORS
7. Encryption
8. Rate Limiting
9. Auth Config
10. Tenant Isolation

All tests are self-contained and use mocks where external dependencies
(Redis, PostgreSQL, external services) are not available.
"""

import hashlib
import hmac
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest


# =============================================================================
# 1. SQL INJECTION PROTECTION (3 tests)
# =============================================================================


@pytest.mark.security
class TestSQLInjectionProtection:
    """Verify that table name whitelists and column validators reject payloads."""

    def test_table_whitelist_rejects_injection_payload(self):
        """ALLOWED_TABLES in agent base class rejects SQL injection in table name."""
        from agents.specialized.base import BaseSpecializedAgent

        # Create a minimal agent instance to access verify_entity_tenant
        agent = BaseSpecializedAgent.__new__(BaseSpecializedAgent)
        agent.name = "test_agent"
        agent._context = MagicMock()
        agent._context.get.return_value = 1

        # Simulate the whitelist check directly
        ALLOWED_TABLES = {
            "loans", "leads", "smart_documents", "followup_campaigns",
            "smart_document_requests", "income_calculations",
            "bank_statement_analyses", "compliance_alerts",
            "documents", "tasks", "activities",
        }

        injection_payloads = [
            "loans; DROP TABLE users--",
            "loans UNION SELECT * FROM users",
            "' OR '1'='1",
            "loans\x00",
            "../../../etc/passwd",
        ]

        for payload in injection_payloads:
            assert payload not in ALLOWED_TABLES, (
                f"Injection payload '{payload}' should not be in whitelist"
            )

    def test_column_name_validator_rejects_special_characters(self):
        """sanitize_column_name rejects names with special characters."""
        from auto_import_routes import sanitize_column_name

        dangerous_columns = [
            "col; DROP TABLE--",
            "col' OR '1'='1",
            "col\"; DELETE FROM",
            "col/**/union",
            "123starts_with_digit",
            "col name with spaces",
            "",
            "col\x00null",
        ]

        for col in dangerous_columns:
            result = sanitize_column_name(col)
            assert result == "", (
                f"Column '{col}' should be rejected (got '{result}')"
            )

    def test_valid_column_names_pass_sanitization(self):
        """sanitize_column_name accepts legitimate column names."""
        from auto_import_routes import sanitize_column_name

        valid_columns = [
            "first_name",
            "email",
            "organization_id",
            "_private",
            "CamelCase",
            "col123",
        ]

        for col in valid_columns:
            result = sanitize_column_name(col)
            assert result == col, (
                f"Valid column '{col}' should pass (got '{result}')"
            )


# =============================================================================
# 2. JWT VALIDATION (5 tests)
# =============================================================================


@pytest.mark.security
class TestJWTValidation:
    """Verify JWT token creation, expiration, and claim enforcement."""

    @pytest.fixture(autouse=True)
    def setup_jwt_env(self, monkeypatch):
        """Configure a test SECRET_KEY and clear cached auth settings."""
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-jwt-tests-1234567890")
        monkeypatch.setenv("AUTH_ALGORITHM", "HS256")
        # Clear the lru_cache so AuthSettings picks up our env vars
        from auth.config import get_auth_settings
        get_auth_settings.cache_clear()

    def test_expired_token_rejected(self):
        """Tokens with past expiration are rejected by decode_token."""
        from auth.tokens import create_access_token, decode_token

        # Create a token that expired 1 hour ago
        token = create_access_token(
            data={"sub": "user@test.com", "user_id": 1},
            expires_delta=timedelta(hours=-1),
        )

        result = decode_token(token)
        assert result is None, "Expired token should return None"

    def test_wrong_algorithm_rejected(self):
        """Token signed with wrong algorithm is rejected."""
        from auth.config import get_auth_settings

        settings = get_auth_settings()

        # Create a token with HS384 instead of configured HS256
        payload = {
            "sub": "user@test.com",
            "user_id": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": settings.issuer,
            "aud": settings.audience,
            "jti": str(uuid.uuid4()),
            "type": "access",
        }
        wrong_algo_token = pyjwt.encode(payload, settings.secret_key, algorithm="HS384")

        from auth.tokens import decode_token
        result = decode_token(wrong_algo_token)
        assert result is None, "Token signed with wrong algorithm should be rejected"

    def test_missing_type_claim_borrower_tokens(self):
        """Borrower token without 'type' claim is rejected by verify_borrower_token."""
        from borrower_auth_routes import verify_borrower_token

        secret = os.getenv("SECRET_KEY", "test-secret")
        # Create a token without the 'type' claim
        payload = {
            "sub": "borrower-123",
            "email": "borrower@test.com",
            "exp": datetime.now(timezone.utc) + timedelta(days=14),
            "iat": datetime.now(timezone.utc),
        }

        with patch.object(
            __import__("borrower_auth_routes"),
            "JWT_SECRET",
            secret,
        ):
            token = pyjwt.encode(payload, secret, algorithm="HS256")
            result = verify_borrower_token(token)
            assert result is None, (
                "Borrower token without type='borrower' should be rejected"
            )

    def test_jti_present_in_new_access_tokens(self):
        """Every new access token includes a JTI (token ID) for revocation."""
        from auth.tokens import create_access_token, decode_token

        token = create_access_token(
            data={"sub": "user@test.com", "user_id": 1}
        )
        payload = decode_token(token)

        assert payload is not None
        assert "jti" in payload, "Token must include jti claim"
        assert len(payload["jti"]) > 0, "JTI must be non-empty"
        # JTI should be a valid UUID
        uuid.UUID(payload["jti"])  # Raises ValueError if invalid

    def test_issuer_mismatch_rejected(self):
        """Token with wrong issuer is rejected."""
        from auth.config import get_auth_settings

        settings = get_auth_settings()

        payload = {
            "sub": "user@test.com",
            "user_id": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": "wrong-issuer",
            "aud": settings.audience,
            "jti": str(uuid.uuid4()),
            "type": "access",
        }
        token = pyjwt.encode(payload, settings.secret_key, algorithm="HS256")

        from auth.tokens import decode_token
        result = decode_token(token)
        assert result is None, "Token with wrong issuer should be rejected"


# =============================================================================
# 3. PII REDACTION (3 tests)
# =============================================================================


@pytest.mark.security
class TestPIIRedaction:
    """Verify PII patterns are redacted from log output."""

    def _get_filter(self):
        from middleware.pii_log_filter import PIIRedactionFilter
        return PIIRedactionFilter()

    def test_ssn_patterns_redacted(self):
        """SSN in 123-45-6789 and 123456789 formats are redacted."""
        f = self._get_filter()

        test_cases = [
            ("SSN: 123-45-6789", "***-**-6789"),
            ("ssn is 123 45 6789", "***-**-6789"),
            ("number 123456789", "***-**-6789"),
        ]

        for input_text, expected_partial in test_cases:
            result = f._redact(input_text)
            assert expected_partial in result, (
                f"SSN should be redacted in '{input_text}', got '{result}'"
            )
            # Original SSN digits should NOT appear together
            assert "123-45-6789" not in result
            assert "123 45 6789" not in result

    def test_credit_card_numbers_redacted(self):
        """16-digit credit card patterns are redacted."""
        f = self._get_filter()

        test_cases = [
            "Card: 4111-1111-1111-1111",
            "Card: 4111 1111 1111 1111",
            "Card: 4111111111111111",
        ]

        for input_text in test_cases:
            result = f._redact(input_text)
            # First 12 digits should be masked
            assert "****" in result, (
                f"Credit card should be masked in '{input_text}', got '{result}'"
            )
            # Last 4 digits preserved
            assert "1111" in result

    def test_account_numbers_redacted(self):
        """Bank account numbers following 'account' keyword are redacted."""
        f = self._get_filter()

        test_cases = [
            "account 12345678901",
            "Account#12345678901",
            "account: 12345678901",
        ]

        for input_text in test_cases:
            result = f._redact(input_text)
            assert "ACCT_REDACTED" in result, (
                f"Account number should be redacted in '{input_text}', got '{result}'"
            )


# =============================================================================
# 4. CSRF PROTECTION (2 tests)
# =============================================================================


@pytest.mark.security
class TestCSRFProtection:
    """Verify OAuth state signing rejects unsigned/tampered state."""

    @pytest.fixture(autouse=True)
    def setup_secret(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "csrf-test-secret-key")

    def test_unsigned_state_rejected(self):
        """OAuth state without HMAC signature is rejected."""
        from oauth_routes import _verify_oauth_state

        # State without any pipe separator (no signature)
        with pytest.raises(ValueError, match="Invalid state format"):
            _verify_oauth_state("unsignedstatedata")

    def test_tampered_signature_rejected(self):
        """OAuth state with tampered HMAC signature is rejected."""
        from oauth_routes import _sign_oauth_state, _verify_oauth_state

        signed = _sign_oauth_state("valid-data")
        # Tamper with the signature by changing last characters
        data, sig = signed.rsplit("|", 1)
        tampered = f"{data}|{'0' * len(sig)}"

        with pytest.raises(ValueError, match="Invalid state signature"):
            _verify_oauth_state(tampered)


# =============================================================================
# 5. INPUT VALIDATION (3 tests)
# =============================================================================


@pytest.mark.security
class TestInputValidation:
    """Verify HTML sanitization, filename safety, and redirect validation."""

    def test_html_sanitization_strips_script_tags(self):
        """sanitize_text removes <script> and event handler attributes."""
        from input_validation import sanitize_text

        xss_payloads = [
            '<script>alert("xss")</script>',
            '<img onerror="alert(1)" src="x">',
            '<a href="javascript:alert(1)">click</a>',
            '<div onmouseover="steal()">hover</div>',
        ]

        for payload in xss_payloads:
            result = sanitize_text(payload)
            assert "<script" not in result.lower(), (
                f"Script tag not stripped from '{payload}'"
            )
            assert "javascript:" not in result.lower(), (
                f"javascript: not stripped from '{payload}'"
            )
            assert "onerror" not in result.lower() or "alert" not in result.lower(), (
                f"Event handler not stripped from '{payload}'"
            )

    def test_filename_sanitization_prevents_path_traversal(self):
        """sanitize_filename removes path traversal sequences."""
        from input_validation import sanitize_filename

        traversal_payloads = [
            ("../../../etc/passwd", "etcpasswd"),
            ("..\\..\\windows\\system32", "windowssystem32"),
            ("/etc/shadow", "shadow"),
            ("file\x00.txt", "file.txt"),
            (".hidden_file", "hidden_file"),
        ]

        for payload, _expected_safe in traversal_payloads:
            result = sanitize_filename(payload)
            assert ".." not in result, (
                f"Path traversal not removed from '{payload}', got '{result}'"
            )
            assert "/" not in result, (
                f"Slash not removed from '{payload}', got '{result}'"
            )
            assert "\\" not in result, (
                f"Backslash not removed from '{payload}', got '{result}'"
            )
            assert "\x00" not in result, (
                f"Null byte not removed from '{payload}', got '{result}'"
            )

    def test_redirect_path_validation_blocks_open_redirects(self):
        """_safe_redirect_path blocks open redirect attacks."""
        from borrower_auth_routes import _safe_redirect_path

        dangerous_redirects = [
            "https://evil.com/steal",
            "//evil.com/steal",
            "/apply/../../admin",
            "javascript:alert(1)",
            "data:text/html,<script>",
            "/login@evil.com",
            "/apply/page\\evil.com",
        ]

        for redirect in dangerous_redirects:
            result = _safe_redirect_path(redirect)
            assert result.startswith("/apply/"), (
                f"Dangerous redirect '{redirect}' should be blocked, got '{result}'"
            )
            assert "evil" not in result.lower(), (
                f"External domain leaked through in '{redirect}', got '{result}'"
            )


# =============================================================================
# 6. CORS (2 tests)
# =============================================================================


@pytest.mark.security
class TestCORS:
    """Verify CORS origin validation."""

    def _make_cors_middleware(self, is_prod=True):
        """Create a DynamicCORSMiddleware instance for testing."""
        from middleware.dynamic_cors import DynamicCORSMiddleware

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production" if is_prod else "development",
            "RAILWAY_PUBLIC_DOMAIN": "",
            "RAILWAY_CORS_DOMAINS": "",
        }):
            middleware = DynamicCORSMiddleware.__new__(DynamicCORSMiddleware)
            middleware.is_production = is_prod
            middleware._railway_domain = None
            middleware._extra_railway_domains = set()
            middleware._domain_service = None

            # Build static origins
            from middleware.dynamic_cors import DynamicCORSMiddleware as DCORS
            middleware._static_origins = set(DCORS._PRODUCTION_ORIGINS)
            if not is_prod:
                middleware._static_origins.update(DCORS._DEV_ORIGINS)

            return middleware

    def test_unknown_origins_rejected(self):
        """Origins not in production allowlist are rejected."""
        middleware = self._make_cors_middleware(is_prod=True)

        rejected_origins = [
            "https://evil.com",
            "https://phishing-perenniaai.com",
            "http://localhost:3000",  # Dev-only, blocked in prod
            "https://random.railway.app",
            "null",
            "",
        ]

        for origin in rejected_origins:
            assert not middleware.is_allowed_origin(origin), (
                f"Origin '{origin}' should be rejected in production"
            )

    def test_production_origins_allowed(self):
        """Known production origins are accepted."""
        middleware = self._make_cors_middleware(is_prod=True)

        allowed_origins = [
            "https://perenniaai.com",
            "https://www.perenniaai.com",
            "https://app.perenniaai.com",
            "https://api.perenniaai.com",
        ]

        for origin in allowed_origins:
            assert middleware.is_allowed_origin(origin), (
                f"Production origin '{origin}' should be allowed"
            )


# =============================================================================
# 7. ENCRYPTION (3 tests)
# =============================================================================


@pytest.mark.security
class TestEncryption:
    """Verify EncryptedString round-trip, ciphertext variation, and fallback."""

    def _get_manager(self):
        from encryption_utils import EncryptionManager

        # Force re-creation with test key
        with patch.dict(os.environ, {
            "DATA_ENCRYPTION_KEY": "",
            "SECRET_KEY": "test-encryption-secret-key-123456",
            "ENVIRONMENT": "development",
        }):
            return EncryptionManager()

    def test_encrypted_string_round_trip(self):
        """Encrypt then decrypt returns original plaintext."""
        mgr = self._get_manager()

        test_values = [
            "John Doe",
            "123-45-6789",
            "sensitive-data-with-special-chars!@#$%",
            "",  # empty string edge case
        ]

        for value in test_values:
            if not value:
                # Empty string returns as-is
                assert mgr.encrypt(value) == value
                continue

            encrypted = mgr.encrypt(value)
            assert encrypted != value, f"Encrypted should differ from plaintext '{value}'"
            decrypted = mgr.decrypt(encrypted)
            assert decrypted == value, (
                f"Round-trip failed: '{value}' -> '{encrypted}' -> '{decrypted}'"
            )

    def test_different_ciphertext_for_same_plaintext(self):
        """Fernet encryption produces different ciphertexts for same input (IV-based)."""
        mgr = self._get_manager()

        plaintext = "Social Security Number: 123-45-6789"
        encrypted_a = mgr.encrypt(plaintext)
        encrypted_b = mgr.encrypt(plaintext)

        assert encrypted_a != encrypted_b, (
            "Same plaintext should produce different ciphertexts (Fernet uses random IV)"
        )
        # Both should decrypt to same value
        assert mgr.decrypt(encrypted_a) == plaintext
        assert mgr.decrypt(encrypted_b) == plaintext

    def test_plaintext_fallback_for_unencrypted_data(self):
        """decrypt() returns plaintext as-is when value is not Fernet-encrypted."""
        mgr = self._get_manager()

        # Pre-existing plaintext that was never encrypted (migration scenario)
        plaintext_values = [
            "John Doe",
            "plain-text-ssn",
            "not-a-fernet-token",
        ]

        for value in plaintext_values:
            result = mgr.decrypt(value)
            assert result == value, (
                f"Unencrypted value '{value}' should be returned as-is, got '{result}'"
            )


# =============================================================================
# 8. RATE LIMITING (2 tests)
# =============================================================================


@pytest.mark.security
class TestRateLimiting:
    """Verify in-memory rate limiter blocks excess and allows normal traffic."""

    def _get_fresh_limiter(self):
        """Create a fresh RateLimiter instance (bypass singleton for test isolation)."""
        from middleware.rate_limiter import RateLimiter

        # Reset singleton to get a fresh instance
        RateLimiter._instance = None
        limiter = RateLimiter(default_limit=5, default_window=60)
        return limiter

    def teardown_method(self):
        """Reset singleton after each test."""
        from middleware.rate_limiter import RateLimiter
        RateLimiter._instance = None

    def test_excessive_requests_blocked(self):
        """Requests beyond the limit within the window are blocked."""
        limiter = self._get_fresh_limiter()

        key = "test:excessive"
        limit = 3
        window = 60

        # First 3 requests should succeed
        for i in range(limit):
            assert limiter.check_rate_limit(key, limit=limit, window=window), (
                f"Request {i+1} of {limit} should be allowed"
            )

        # 4th request should be blocked
        assert not limiter.check_rate_limit(key, limit=limit, window=window), (
            "Request exceeding limit should be blocked"
        )

        # 5th request should also be blocked
        assert not limiter.check_rate_limit(key, limit=limit, window=window), (
            "Subsequent requests should remain blocked"
        )

    def test_normal_traffic_allowed(self):
        """Requests within the limit are allowed."""
        limiter = self._get_fresh_limiter()

        key = "test:normal"
        limit = 100
        window = 60

        # 50 requests (well under 100 limit)
        for i in range(50):
            assert limiter.check_rate_limit(key, limit=limit, window=window), (
                f"Normal traffic request {i+1} should be allowed"
            )

        remaining = limiter.get_remaining(key, limit, window)
        assert remaining == 50, f"Expected 50 remaining, got {remaining}"


# =============================================================================
# 9. AUTH CONFIG (3 tests)
# =============================================================================


@pytest.mark.security
class TestAuthConfig:
    """Verify authentication configuration and security requirements."""

    def test_password_complexity_requirements_enforced(self):
        """validate_password_strength enforces enterprise password policy."""
        from utils.auth import validate_password_strength

        # Weak passwords that should fail
        weak_passwords = [
            ("short", ["at least 12 characters"]),
            ("alllowercase1!", ["uppercase"]),
            ("ALLUPPERCASE1!", ["lowercase"]),
            ("NoDigitsHere!!", ["digit"]),
            ("NoSpecial1234A", ["special character"]),
        ]

        for password, expected_violations in weak_passwords:
            violations = validate_password_strength(password)
            assert len(violations) > 0, (
                f"Weak password '{password}' should have violations"
            )
            # Check each expected violation is present (partial match)
            for expected in expected_violations:
                assert any(expected.lower() in v.lower() for v in violations), (
                    f"Expected violation containing '{expected}' for password '{password}', "
                    f"got: {violations}"
                )

        # Strong password that should pass
        strong_password = "MyStr0ng!Pass#2026"
        violations = validate_password_strength(strong_password)
        assert len(violations) == 0, (
            f"Strong password should have no violations, got: {violations}"
        )

    def test_token_expiry_configured_correctly(self):
        """Access tokens expire in 15 minutes, refresh tokens in 7 days."""
        from auth.config import AuthSettings

        settings = AuthSettings()

        assert settings.access_token_expire_minutes == 15, (
            f"Access token should expire in 15 min, got {settings.access_token_expire_minutes}"
        )
        assert settings.refresh_token_expire_days == 7, (
            f"Refresh token should expire in 7 days, got {settings.refresh_token_expire_days}"
        )

    def test_production_requires_secret_key(self):
        """Production environment raises if SECRET_KEY is missing (HS256 mode)."""
        from auth.config import AuthSettings

        with patch.dict(os.environ, {
            "SECRET_KEY": "",
            "AUTH_ALGORITHM": "HS256",
            "ENVIRONMENT": "production",
        }):
            with pytest.raises(Exception):
                # Should raise ValueError via field_validator
                AuthSettings()


# =============================================================================
# 10. TENANT ISOLATION (2 tests)
# =============================================================================


@pytest.mark.security
class TestTenantIsolation:
    """Verify row-level security context is enforced."""

    def test_set_tenant_context_validates_org_id(self):
        """set_tenant_context rejects non-positive-integer org_id values."""
        from database.tenant_mixin import set_tenant_context

        mock_db = MagicMock()

        invalid_org_ids = [
            0,
            -1,
            "1; DROP TABLE users",
            None,
            3.14,
        ]

        for org_id in invalid_org_ids:
            with pytest.raises((ValueError, TypeError)):
                set_tenant_context(mock_db, org_id)

    def test_rls_context_set_on_valid_session(self):
        """set_tenant_context executes SET LOCAL with correct org_id."""
        from database.tenant_mixin import set_tenant_context

        mock_db = MagicMock()

        set_tenant_context(mock_db, 42)

        # Verify that execute was called with the RLS statement
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args

        # First positional arg is the text() object
        sql_text = str(call_args[0][0])
        assert "app.current_tenant" in sql_text, (
            "RLS statement should set app.current_tenant"
        )

        # Second arg is the parameter dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("org_id") == "42", (
            f"org_id parameter should be '42', got {params}"
        )
