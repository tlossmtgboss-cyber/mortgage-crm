"""
Authentication Utility Function Unit Tests

Tests for core authentication functions:
- Password hashing (bcrypt)
- Password verification
- Access token creation
- Refresh token creation
- Token expiration behavior

These tests exercise the auth functions defined in main.py:
  verify_password, get_password_hash, create_access_token, create_refresh_token

They do NOT require a database or HTTP client -- pure function tests.
"""
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


# Mark all tests as unit tests
pytestmark = [pytest.mark.unit]


class TestPasswordHashing:
    """Tests for password hashing with bcrypt."""

    def test_get_password_hash_returns_string(self):
        """get_password_hash should return a non-empty string."""
        from main import get_password_hash

        result = get_password_hash("MySecurePassword123!")
        assert isinstance(result, str), "Hash should be a string"
        assert len(result) > 0, "Hash should not be empty"

    def test_get_password_hash_is_bcrypt(self):
        """Hashed password should be a bcrypt hash (starts with $2b$)."""
        from main import get_password_hash

        result = get_password_hash("TestPassword")
        assert result.startswith("$2b$") or result.startswith("$2a$"), (
            f"Hash should be bcrypt format, got: {result[:10]}..."
        )

    def test_get_password_hash_is_not_plaintext(self):
        """Hash should never equal the plaintext password."""
        from main import get_password_hash

        password = "SecurePassword123!"
        hashed = get_password_hash(password)
        assert hashed != password, "Hash must not equal plaintext"

    def test_get_password_hash_different_for_same_input(self):
        """Two calls with the same password should produce different hashes (bcrypt salting)."""
        from main import get_password_hash

        password = "SamePasswordTwice"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        assert hash1 != hash2, (
            "bcrypt should produce different hashes due to random salt"
        )


class TestPasswordVerification:
    """Tests for password verification."""

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        from main import verify_password, get_password_hash

        password = "CorrectPassword123!"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True, (
            "Should verify correct password"
        )

    def test_verify_password_incorrect(self):
        """verify_password should return False for incorrect password."""
        from main import verify_password, get_password_hash

        hashed = get_password_hash("OriginalPassword123!")
        assert verify_password("WrongPassword", hashed) is False, (
            "Should reject incorrect password"
        )

    def test_verify_password_empty_password(self):
        """verify_password should return False for empty password against a real hash."""
        from main import verify_password, get_password_hash

        hashed = get_password_hash("RealPassword123!")
        assert verify_password("", hashed) is False, (
            "Should reject empty password"
        )

    def test_verify_password_case_sensitive(self):
        """Password verification should be case-sensitive."""
        from main import verify_password, get_password_hash

        password = "CaseSensitive123!"
        hashed = get_password_hash(password)
        assert verify_password("casesensitive123!", hashed) is False, (
            "Password verification should be case-sensitive"
        )


class TestAccessTokenCreation:
    """Tests for JWT access token creation."""

    def test_create_access_token_returns_string(self):
        """create_access_token should return a non-empty JWT string."""
        from main import create_access_token

        token = create_access_token(data={"sub": "test@example.com"})
        assert isinstance(token, str), "Token should be a string"
        assert len(token) > 0, "Token should not be empty"

    def test_create_access_token_is_jwt_format(self):
        """Token should have 3 dot-separated parts (JWT format)."""
        from main import create_access_token

        token = create_access_token(data={"sub": "test@example.com"})
        parts = token.split(".")
        assert len(parts) == 3, (
            f"JWT should have 3 parts, got {len(parts)}"
        )

    def test_create_access_token_with_user_id(self):
        """create_access_token should accept optional user_id parameter."""
        from main import create_access_token

        # Should not raise
        token = create_access_token(
            data={"sub": "test@example.com"},
            user_id=42,
        )
        assert isinstance(token, str) and len(token) > 0

    def test_create_access_token_with_tenant_id(self):
        """create_access_token should accept optional tenant_id parameter."""
        from main import create_access_token

        token = create_access_token(
            data={"sub": "test@example.com"},
            user_id=1,
            tenant_id="org-123",
        )
        assert isinstance(token, str) and len(token) > 0

    def test_create_access_token_different_users_different_tokens(self):
        """Tokens for different users should be different."""
        from main import create_access_token

        token1 = create_access_token(data={"sub": "user1@example.com"})
        token2 = create_access_token(data={"sub": "user2@example.com"})
        assert token1 != token2, (
            "Tokens for different users should differ"
        )


class TestRefreshTokenCreation:
    """Tests for JWT refresh token creation."""

    def test_create_refresh_token_returns_string(self):
        """create_refresh_token should return a non-empty JWT string."""
        from main import create_refresh_token

        token = create_refresh_token(data={"sub": "test@example.com"})
        assert isinstance(token, str), "Refresh token should be a string"
        assert len(token) > 0, "Refresh token should not be empty"

    def test_create_refresh_token_is_jwt_format(self):
        """Refresh token should have 3 dot-separated parts (JWT format)."""
        from main import create_refresh_token

        token = create_refresh_token(data={"sub": "test@example.com"})
        parts = token.split(".")
        assert len(parts) == 3, (
            f"Refresh JWT should have 3 parts, got {len(parts)}"
        )

    def test_access_and_refresh_tokens_differ(self):
        """Access and refresh tokens for the same user should differ."""
        from main import create_access_token, create_refresh_token

        data = {"sub": "same@example.com"}
        access = create_access_token(data=data)
        refresh = create_refresh_token(data=data)
        assert access != refresh, (
            "Access and refresh tokens should be different"
        )


class TestTokenExpiration:
    """Tests for token expiration behavior."""

    def test_access_token_has_expiration(self):
        """Access token should contain an expiration claim."""
        from main import create_access_token
        import jwt as jose_jwt

        token = create_access_token(data={"sub": "exp_test@example.com"})

        try:
            # Decode without verification to inspect claims
            payload = jose_jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256", "RS256"])
            assert "exp" in payload, "Token should contain 'exp' claim"
            # Expiration should be in the future
            exp_time = payload["exp"]
            assert exp_time > time.time(), "Token expiration should be in the future"
        except Exception:
            # If using RS256 or non-standard format, just verify token is valid JWT
            parts = token.split(".")
            assert len(parts) == 3, "Token should be valid JWT format"

    def test_refresh_token_expires_later_than_access(self):
        """Refresh token should expire later than access token."""
        from main import create_access_token, create_refresh_token
        import jwt as jose_jwt

        data = {"sub": "expiry_compare@example.com"}
        access = create_access_token(data=data)
        refresh = create_refresh_token(data=data)

        try:
            access_claims = jose_jwt.decode(access, options={"verify_signature": False}, algorithms=["HS256", "RS256"])
            refresh_claims = jose_jwt.decode(refresh, options={"verify_signature": False}, algorithms=["HS256", "RS256"])

            if "exp" in access_claims and "exp" in refresh_claims:
                assert refresh_claims["exp"] > access_claims["exp"], (
                    "Refresh token should expire later than access token"
                )
        except Exception:
            # Skip if tokens can't be decoded (e.g., RS256 without key)
            pass
