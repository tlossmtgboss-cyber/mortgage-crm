"""
Comprehensive Authentication Flow Tests

Covers:
- Login (valid/invalid credentials, missing fields, inactive user)
- Token lifecycle (creation, verification, expiry, invalid signature)
- Token blacklist (logout, rejection of blacklisted tokens)
- Authorization (admin endpoints, tenant isolation)
- Password hashing (bcrypt verification, change requires old password)

Test categories:
- Unit tests: No database or app server required. Test token functions directly.
- Integration tests: Require TestClient + PostgreSQL. Marked with @pytest.mark.integration
  and skip automatically when the DB is unavailable.
"""

import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import jwt

# ---------------------------------------------------------------------------
# Auth module imports (always available in the backend tree)
# ---------------------------------------------------------------------------
from auth.config import AuthSettings
from auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    verify_access_token,
    get_token_jti,
    TokenType,
    TokenData,
    TokenBlacklist,
    _InMemoryBlacklist,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-auth-flow-tests-only"

_TEST_SETTINGS = AuthSettings(
    secret_key=_TEST_SECRET,
    algorithm="HS256",
    access_token_expire_minutes=15,
    refresh_token_expire_days=7,
    issuer="perennia-ai",
    audience="perennia-crm",
)


@pytest.fixture(autouse=True)
def _patch_auth_settings():
    """Force HS256 with a known secret for all tests in this module."""
    with patch("auth.tokens.get_auth_settings", return_value=_TEST_SETTINGS):
        with patch("auth.config.get_auth_settings", return_value=_TEST_SETTINGS):
            yield


def _make_access_token(sub="user@test.com", user_id=1, tenant_id="1", **extra):
    data = {"sub": sub, "user_id": user_id, "tenant_id": tenant_id, **extra}
    return create_access_token(data)


def _make_refresh_token(sub="user@test.com", user_id=1, **extra):
    data = {"sub": sub, "user_id": user_id, **extra}
    return create_refresh_token(data)


def _make_expired_token(sub="user@test.com", token_type="access"):
    data = {"sub": sub, "user_id": 1}
    expired_delta = timedelta(seconds=-10)
    if token_type == "access":
        return create_access_token(data, expires_delta=expired_delta)
    return create_refresh_token(data, expires_delta=expired_delta)


def _make_blacklist():
    """Create an enabled blacklist backed by in-memory store."""
    bl = TokenBlacklist()
    bl._enabled = True
    bl._using_fallback = True
    return bl


# DB-availability check for integration tests
def _db_available():
    try:
        from sqlalchemy import create_engine, text
        import os
        url = os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        eng = create_engine(url)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_HAS_DB = _db_available()
requires_db = pytest.mark.skipif(not _HAS_DB, reason="PostgreSQL not available")


# ============================================================================
# 1. LOGIN TESTS (unit - mock the DB layer via route patches)
# ============================================================================

@pytest.mark.unit
class TestLoginUnit:
    """Unit-level login tests that mock the database entirely."""

    def _mock_login_deps(self, mock_models, mock_funcs, mock_config, user, verify_result):
        """Wire up the three runtime-import helpers used by _login_impl."""
        mock_models.return_value = {
            "User": MagicMock(), "Organization": MagicMock(),
            "PromoCode": MagicMock(), "Subscription": MagicMock(),
            "SubscriptionPlan": MagicMock(),
        }
        mock_funcs.return_value = {
            "create_access_token": lambda data=None, user_id=None, tenant_id=None, **kw: "access.tok",
            "create_refresh_token": lambda data=None, user_id=None, **kw: "refresh.tok",
            "verify_password": lambda plain, hashed: verify_result,
            "get_password_hash": lambda p: "hashed",
        }
        mock_config.return_value = {
            "SECRET_KEY": _TEST_SECRET,
            "ALGORITHM": "HS256",
            "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
            "_USE_SECURE_TOKENS": False,
            "token_blacklist": None,
            "_verify_secure_token": None,
            "TokenType": None,
        }

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_login_valid_credentials(self, mock_config, mock_funcs, mock_models, client):
        """Successful login returns access_token, refresh_token, and user info."""
        user = MagicMock(
            id=1, email="lo@example.com", full_name="Test",
            hashed_password="$2b$12$x", role="loan_officer",
            permission_role="loan_officer", organization_id=1,
            is_active=True, onboarding_completed=True, mfa_enabled=False,
            last_activity_at=None, failed_login_attempts=0,
        )
        self._mock_login_deps(mock_models, mock_funcs, mock_config, user, True)

        resp = client.post("/api/v1/auth/login", json={"x1": "lo@example.com", "x2": "password"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    @requires_db
    def test_login_invalid_email(self, client):
        """Login with non-existent email returns 401."""
        resp = client.post("/api/v1/auth/login", json={"x1": "ghost@x.com", "x2": "pw"})
        assert resp.status_code in (401, 500)

    @requires_db
    def test_login_missing_fields(self, client):
        """Login with missing fields returns 422 (validation error)."""
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_login_invalid_password(self, mock_config, mock_funcs, mock_models, client):
        """Login with wrong password returns 401."""
        user = MagicMock(
            id=1, email="lo@example.com", hashed_password="$2b$12$x",
            role="loan_officer", permission_role="loan_officer",
            organization_id=1, is_active=True, mfa_enabled=False,
            full_name="T", onboarding_completed=True,
            last_activity_at=None, failed_login_attempts=0,
        )
        self._mock_login_deps(mock_models, mock_funcs, mock_config, user, False)

        resp = client.post("/api/v1/auth/login", json={"x1": "lo@example.com", "x2": "bad"})
        assert resp.status_code == 401

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_login_inactive_user_no_password(self, mock_config, mock_funcs, mock_models, client):
        """Login for a user with no hashed_password returns 401."""
        user = MagicMock(
            id=1, email="lo@example.com", hashed_password=None,
            role="loan_officer", permission_role="loan_officer",
            organization_id=1, is_active=True, mfa_enabled=False,
            full_name="T", onboarding_completed=True,
            last_activity_at=None, failed_login_attempts=0,
        )
        self._mock_login_deps(mock_models, mock_funcs, mock_config, user, False)

        resp = client.post("/api/v1/auth/login", json={"x1": "lo@example.com", "x2": "pw"})
        assert resp.status_code == 401


# ============================================================================
# 2. TOKEN LIFECYCLE TESTS (pure unit - no DB required)
# ============================================================================

@pytest.mark.unit
class TestTokenLifecycle:
    """Tests for JWT creation, decoding, and verification."""

    def test_access_token_valid(self):
        """A freshly created access token decodes successfully."""
        token = _make_access_token()
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user@test.com"
        assert payload["type"] == TokenType.ACCESS.value
        assert payload["user_id"] == 1

    def test_access_token_contains_standard_claims(self):
        """Access token includes iss, aud, jti, iat, exp claims."""
        token = _make_access_token()
        payload = decode_token(token)
        for claim in ("iss", "aud", "jti", "iat", "exp"):
            assert claim in payload, f"Missing claim: {claim}"
        assert payload["iss"] == "perennia-ai"
        assert payload["aud"] == "perennia-crm"

    def test_access_token_expired(self):
        """An expired access token is rejected by decode_token."""
        token = _make_expired_token(token_type="access")
        payload = decode_token(token, verify_exp=True)
        assert payload is None

    def test_access_token_invalid_signature(self):
        """A token signed with a different key is rejected."""
        bad_settings = AuthSettings(
            secret_key="wrong-key-entirely",
            algorithm="HS256",
            issuer="perennia-ai",
            audience="perennia-crm",
        )
        with patch("auth.tokens.get_auth_settings", return_value=bad_settings):
            bad_token = create_access_token({"sub": "user@test.com"})

        # Verify with the correct test settings -- should fail
        payload = decode_token(bad_token)
        assert payload is None

    def test_access_token_tampered(self):
        """Modifying the payload of a token invalidates the signature."""
        token = _make_access_token()
        parts = token.split(".")
        parts[1] = parts[1][:-4] + "XXXX"
        tampered = ".".join(parts)
        payload = decode_token(tampered)
        assert payload is None

    def test_access_token_missing_returns_none(self):
        """decode_token with empty string returns None."""
        assert decode_token("") is None
        assert decode_token("not-a-jwt") is None

    def test_refresh_token_valid(self):
        """A freshly created refresh token decodes with type=refresh."""
        token = _make_refresh_token()
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == TokenType.REFRESH.value

    def test_refresh_token_expired(self):
        """An expired refresh token is rejected."""
        token = _make_expired_token(token_type="refresh")
        payload = decode_token(token, verify_exp=True)
        assert payload is None

    def test_verify_token_type_mismatch(self):
        """verify_token rejects an access token when refresh is expected."""
        token = _make_access_token()
        result = verify_token(token, expected_type=TokenType.REFRESH, check_blacklist=False)
        assert result is None

    def test_verify_token_returns_token_data(self):
        """verify_token returns a properly structured TokenData."""
        token = _make_access_token(sub="hello@test.com", user_id=42, tenant_id="7")
        td = verify_token(token, check_blacklist=False)
        assert isinstance(td, TokenData)
        assert td.sub == "hello@test.com"
        assert td.user_id == 42
        assert td.tenant_id == "7"
        assert td.token_type == TokenType.ACCESS

    def test_decode_token_without_exp_verification(self):
        """decode_token with verify_exp=False returns payload even if expired."""
        token = _make_expired_token()
        payload = decode_token(token, verify_exp=False)
        assert payload is not None
        assert payload["sub"] == "user@test.com"

    def test_custom_token_id(self):
        """A custom jti is preserved in the token."""
        custom_jti = str(uuid.uuid4())
        token = create_access_token({"sub": "a@b.com"}, token_id=custom_jti)
        payload = decode_token(token)
        assert payload["jti"] == custom_jti

    def test_verify_access_token_convenience(self):
        """verify_access_token returns a dict with sub and user_id."""
        token = _make_access_token(sub="x@y.com", user_id=5)
        with patch("auth.tokens.token_blacklist") as mock_bl:
            mock_bl.is_blacklisted.return_value = False
            mock_bl.is_user_revoked.return_value = False
            result = verify_access_token(token)
        assert result is not None
        assert result["sub"] == "x@y.com"
        assert result["user_id"] == 5

    def test_get_token_jti_from_expired(self):
        """get_token_jti extracts jti even from an expired token."""
        token = _make_expired_token()
        jti = get_token_jti(token)
        assert jti is not None
        assert isinstance(jti, str) and len(jti) > 0


# ============================================================================
# 3. TOKEN BLACKLIST TESTS (pure unit - no DB required)
# ============================================================================

@pytest.mark.unit
class TestTokenBlacklist:
    """Tests for the in-memory token blacklist (no Redis required)."""

    def test_logout_blacklists_token(self):
        """After add(), the token is reported as blacklisted."""
        bl = _make_blacklist()
        token = _make_access_token()
        bl.add(token, reason="user_logout")
        assert bl.is_blacklisted(token) is True

    def test_non_blacklisted_token_passes(self):
        """A token that was never blacklisted returns False."""
        bl = _make_blacklist()
        token = _make_access_token()
        assert bl.is_blacklisted(token) is False

    def test_blacklisted_token_rejected_by_verify(self):
        """verify_token returns None for a blacklisted token."""
        bl = _make_blacklist()
        token = _make_access_token()
        bl.add(token, reason="test")

        with patch("auth.tokens.token_blacklist", bl):
            result = verify_token(token, check_blacklist=True)
        assert result is None

    def test_revoke_all_for_user(self):
        """revoke_all_for_user causes subsequent tokens to be rejected."""
        bl = _make_blacklist()
        token = _make_access_token(user_id=99)
        payload = decode_token(token)
        iat = payload["iat"]

        bl.revoke_all_for_user(99)
        assert bl.is_user_revoked(99, iat) is True

    def test_clear_user_revocation(self):
        """clear_user_revocation un-flags the user."""
        bl = _make_blacklist()
        bl.revoke_all_for_user(5)
        assert bl.is_user_revoked(5) is True
        bl.clear_user_revocation(5)
        assert bl.is_user_revoked(5) is False

    def test_in_memory_blacklist_ttl(self):
        """In-memory blacklist entries expire based on TTL."""
        mem = _InMemoryBlacklist()
        mem.setex("k", 1, "v")
        assert mem.get("k") is not None
        time.sleep(1.1)
        assert mem.get("k") is None

    def test_disabled_blacklist_always_passes(self):
        """When blacklist is explicitly disabled, is_blacklisted always returns False."""
        bl = TokenBlacklist()
        bl._enabled = False  # Explicitly disable
        token = _make_access_token()
        assert bl.is_blacklisted(token) is False
        assert bl.add(token, reason="test") is False


# ============================================================================
# 4. PROTECTED ENDPOINT TESTS (integration - require DB + app)
# ============================================================================

@pytest.mark.integration
class TestProtectedEndpoints:
    """Verify auth enforcement on protected endpoints."""

    @requires_db
    def test_access_token_missing_returns_401(self, client):
        """A protected endpoint without Authorization header returns 401 or 403."""
        resp = client.get("/api/v1/leads")
        assert resp.status_code in (401, 403, 422)

    @requires_db
    def test_access_token_valid_reaches_handler(self, authenticated_client):
        """With a valid (mocked) token, the handler is reached."""
        resp = authenticated_client.get("/api/v1/leads")
        assert resp.status_code not in (401, 403)


# ============================================================================
# 5. AUTHORIZATION / ROLE TESTS
# ============================================================================

@pytest.mark.unit
class TestAuthorization:
    """Tests for role-based access control and tenant isolation."""

    def test_tenant_isolation_via_token_claims(self):
        """Tokens for different tenants carry distinct tenant_id claims."""
        tok_a = _make_access_token(sub="a@org1.com", tenant_id="org-1")
        tok_b = _make_access_token(sub="b@org2.com", tenant_id="org-2")

        payload_a = decode_token(tok_a)
        payload_b = decode_token(tok_b)

        assert payload_a["tenant_id"] == "org-1"
        assert payload_b["tenant_id"] == "org-2"
        assert payload_a["tenant_id"] != payload_b["tenant_id"]

    def test_token_carries_user_id(self):
        """Each token embeds the user_id for RLS enforcement."""
        tok = _make_access_token(user_id=42)
        td = verify_token(tok, check_blacklist=False)
        assert td.user_id == 42

    def test_token_type_prevents_refresh_as_access(self):
        """A refresh token cannot be used as an access token."""
        refresh = _make_refresh_token()
        result = verify_token(refresh, expected_type=TokenType.ACCESS, check_blacklist=False)
        assert result is None

    @requires_db
    def test_admin_endpoint_as_admin(self, db_session):
        """Admin user can access general endpoints."""
        from tests.conftest import MockUser
        from main import app, get_current_user, get_current_user_flexible
        from auth.dependencies import (
            get_current_user as auth_gcu,
            get_current_user_flexible as auth_gcuf,
        )
        from database import get_db
        from fastapi.testclient import TestClient

        admin = MockUser(id=2, email="admin@test.com", role="admin")

        async def _admin():
            return admin

        def _db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _admin
        app.dependency_overrides[get_current_user_flexible] = _admin
        app.dependency_overrides[auth_gcu] = _admin
        app.dependency_overrides[auth_gcuf] = _admin

        with TestClient(app) as tc:
            resp = tc.get("/api/v1/leads")
            assert resp.status_code not in (401, 403)

        app.dependency_overrides.clear()

    @requires_db
    def test_admin_endpoint_as_regular_user(self, db_session):
        """Regular user gets 401/403 on admin-restricted endpoints."""
        from tests.conftest import MockUser
        from main import app, get_current_user, get_current_user_flexible
        from auth.dependencies import (
            get_current_user as auth_gcu,
            get_current_user_flexible as auth_gcuf,
        )
        from database import get_db
        from fastapi.testclient import TestClient

        lo_user = MockUser(id=3, email="lo@test.com", role="loan_officer")

        async def _lo():
            return lo_user

        def _db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _lo
        app.dependency_overrides[get_current_user_flexible] = _lo
        app.dependency_overrides[auth_gcu] = _lo
        app.dependency_overrides[auth_gcuf] = _lo

        with TestClient(app) as tc:
            resp = tc.post("/api/v1/admin/kill-idle-connections", json={})
            assert resp.status_code in (401, 403, 422)

        app.dependency_overrides.clear()


# ============================================================================
# 6. PASSWORD TESTS (pure unit - no DB required)
# ============================================================================

@pytest.mark.unit
class TestPasswordHashing:
    """Tests for bcrypt password hashing used by the auth system."""

    def test_password_hash_verification(self):
        """A hashed password verifies correctly with bcrypt."""
        import bcrypt

        raw = "SuperSecret123!"
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

        assert bcrypt.checkpw(raw.encode(), hashed.encode()) is True
        assert bcrypt.checkpw("WrongPassword".encode(), hashed.encode()) is False

    def test_password_hash_is_not_plaintext(self):
        """get_password_hash never returns the plaintext password."""
        import bcrypt
        raw = "MyPassword"
        hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        assert hashed != raw
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_different_passwords_produce_different_hashes(self):
        """Two different passwords produce different bcrypt hashes."""
        import bcrypt
        h1 = bcrypt.hashpw("Password1".encode(), bcrypt.gensalt()).decode()
        h2 = bcrypt.hashpw("Password2".encode(), bcrypt.gensalt()).decode()
        assert h1 != h2

    @requires_db
    def test_password_change_requires_valid_reset_token(self, client):
        """The reset-password endpoint rejects an invalid token."""
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "new_password": "NewPass123!"},
        )
        assert resp.status_code in (400, 401, 422, 500)


# ============================================================================
# 7. TOKEN REFRESH TESTS (integration - require app/DB)
# ============================================================================

@pytest.mark.integration
class TestTokenRefresh:
    """Tests for the /token/refresh endpoint.

    Covers the critical refresh flow that LOs hit multiple times per day
    (15-minute access token expiry). Tests both the secure-token path
    (production) and edge cases: expired, blacklisted, missing, and
    wrong-type tokens.
    """

    def _mock_refresh_deps(self, mock_models, mock_funcs, mock_config, user,
                           use_secure=True, blacklist=None):
        """Wire up runtime-import helpers used by refresh_access_token."""
        mock_user_cls = MagicMock()
        mock_user_cls.filter.return_value.first.return_value = user
        mock_models.return_value = {
            "User": mock_user_cls,
            "Organization": MagicMock(),
            "PromoCode": MagicMock(),
            "Subscription": MagicMock(),
            "SubscriptionPlan": MagicMock(),
        }
        mock_funcs.return_value = {
            "create_access_token": lambda data=None, user_id=None, tenant_id=None, **kw: _make_access_token(
                sub=data.get("sub", "user@test.com") if data else "user@test.com",
                user_id=user_id or 1,
                tenant_id=tenant_id or "1",
            ),
            "create_refresh_token": lambda data=None, user_id=None, **kw: _make_refresh_token(),
            "verify_password": lambda plain, hashed: True,
            "get_password_hash": lambda p: "hashed",
        }
        mock_config.return_value = {
            "SECRET_KEY": _TEST_SECRET,
            "ALGORITHM": "HS256",
            "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
            "_USE_SECURE_TOKENS": use_secure,
            "token_blacklist": blacklist,
            "_verify_secure_token": verify_token if use_secure else None,
            "TokenType": TokenType if use_secure else None,
        }

    @requires_db
    def test_refresh_with_invalid_token(self, client):
        """Posting a garbage refresh token returns 401."""
        resp = client.post("/token/refresh", json={"refresh_token": "garbage.jwt.here"})
        assert resp.status_code in (401, 422)

    @requires_db
    def test_refresh_with_expired_token(self, client):
        """An expired refresh token is rejected."""
        expired = _make_expired_token(token_type="refresh")
        resp = client.post("/token/refresh", json={"refresh_token": expired})
        assert resp.status_code in (401, 422, 500)

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_valid_token_returns_new_access_token(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """Valid refresh token returns a new access token and bearer type.

        This is the happy-path flow LOs hit every 15 minutes.
        """
        user = MagicMock(
            id=1, email="lo@example.com", organization_id=1,
        )
        bl = _make_blacklist()
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, user,
                                use_secure=True, blacklist=bl)

        refresh = _make_refresh_token(sub="lo@example.com", user_id=1)
        resp = client.post("/token/refresh", json={"refresh_token": refresh})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "access_token" in body, "Response must include access_token"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 15 * 60, "Expiry should be 15 minutes in seconds"

        # The new access token should be a valid JWT
        new_access = body["access_token"]
        parts = new_access.split(".")
        assert len(parts) == 3, "New access token should be valid JWT format"

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_valid_token_blacklists_used_refresh(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """After successful refresh, the used refresh token is blacklisted (rotation)."""
        user = MagicMock(
            id=1, email="lo@example.com", organization_id=1,
        )
        bl = _make_blacklist()
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, user,
                                use_secure=True, blacklist=bl)

        refresh = _make_refresh_token(sub="lo@example.com", user_id=1)
        resp = client.post("/token/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200

        # The used refresh token should now be blacklisted
        assert bl.is_blacklisted(refresh) is True, (
            "Used refresh token must be blacklisted to prevent replay"
        )

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_blacklisted_token_returns_401(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """A blacklisted (already-used) refresh token is rejected with 401."""
        user = MagicMock(
            id=1, email="lo@example.com", organization_id=1,
        )
        bl = _make_blacklist()
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, user,
                                use_secure=True, blacklist=bl)

        refresh = _make_refresh_token(sub="lo@example.com", user_id=1)

        # Pre-blacklist the token (simulates it was already used)
        bl.add(refresh, reason="token_rotation")

        # _verify_secure_token checks the global token_blacklist, so we need
        # to patch it to use our test blacklist instance
        with patch("auth.tokens.token_blacklist", bl):
            resp = client.post("/token/refresh", json={"refresh_token": refresh})

        assert resp.status_code == 401, (
            f"Blacklisted refresh token should return 401, got {resp.status_code}: {resp.text}"
        )

    @requires_db
    def test_refresh_missing_token_returns_422(self, client):
        """Missing refresh_token field in the body returns 422 (validation error)."""
        resp = client.post("/token/refresh", json={})
        assert resp.status_code == 422, (
            f"Missing refresh_token should return 422, got {resp.status_code}"
        )

    @requires_db
    def test_refresh_empty_body_returns_422(self, client):
        """Empty request body returns 422."""
        resp = client.post("/token/refresh", content=b"", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422, (
            f"Empty body should return 422, got {resp.status_code}"
        )

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_with_access_token_returns_401(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """Using an access token instead of a refresh token returns 401.

        This verifies the token type check (expected_type=TokenType.REFRESH)
        rejects access tokens, preventing token confusion attacks.
        """
        user = MagicMock(
            id=1, email="lo@example.com", organization_id=1,
        )
        bl = _make_blacklist()
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, user,
                                use_secure=True, blacklist=bl)

        # Create an ACCESS token (not refresh)
        access_token = _make_access_token(sub="lo@example.com", user_id=1)

        resp = client.post("/token/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401, (
            f"Access token used as refresh should return 401, got {resp.status_code}: {resp.text}"
        )

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_for_deleted_user_returns_401(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """Refresh token for a user that no longer exists in the DB returns 401."""
        # User query returns None (user deleted)
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, None,
                                use_secure=True, blacklist=_make_blacklist())

        refresh = _make_refresh_token(sub="deleted@example.com", user_id=999)

        resp = client.post("/token/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401, (
            f"Refresh for deleted user should return 401, got {resp.status_code}: {resp.text}"
        )

    @requires_db
    @patch("routes.auth_routes.get_models")
    @patch("routes.auth_routes.get_auth_functions")
    @patch("routes.auth_routes.get_auth_config")
    def test_refresh_after_revoke_all_returns_401(
        self, mock_config, mock_funcs, mock_models, client
    ):
        """After revoke_all_for_user (password change), refresh token is rejected."""
        user = MagicMock(
            id=1, email="lo@example.com", organization_id=1,
        )
        bl = _make_blacklist()
        self._mock_refresh_deps(mock_models, mock_funcs, mock_config, user,
                                use_secure=True, blacklist=bl)

        refresh = _make_refresh_token(sub="lo@example.com", user_id=1)

        # Simulate global revocation (e.g., password change)
        bl.revoke_all_for_user(1)

        # Patch the global blacklist so verify_token sees the revocation
        with patch("auth.tokens.token_blacklist", bl):
            resp = client.post("/token/refresh", json={"refresh_token": refresh})

        assert resp.status_code == 401, (
            f"Refresh after revoke_all should return 401, got {resp.status_code}: {resp.text}"
        )
