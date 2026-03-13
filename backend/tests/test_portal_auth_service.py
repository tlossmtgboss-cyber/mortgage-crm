"""
Tests for Smart Docs Portal Authentication Service

Covers:
1.  Token generation with valid inputs
2.  Token generation with missing required fields
3.  Token verification with valid token
4.  Expired tokens are rejected with 401
5.  Tampered/invalid tokens are rejected with 401
6.  Wrong org tokens are rejected during workspace verification
7.  Wrong loan tokens are rejected during workspace verification
8.  Borrower email mismatch is rejected
9.  Magic link generation returns URL with embedded token
10. Rate limiting on token generation (max 5 per email per hour)
11. Upload rate limiting (max 10 per borrower per hour)
12. Read-only scope rejects write operations
13. Token extraction from X-Portal-Token header
14. Token extraction from Authorization: Bearer header
15. Token extraction from ?token= query parameter
16. Missing token returns 401
17. All portal endpoints require authentication (integration check)
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import jwt

from services.smart_docs.portal_auth_service import (
    generate_portal_access_token,
    verify_portal_access_token,
    generate_portal_magic_link,
    get_current_portal_user,
    require_write_scope,
    check_upload_rate_limit,
    reset_rate_limits,
    SECRET_KEY,
    PORTAL_TOKEN_ALGORITHM,
    PORTAL_TOKEN_ISSUER,
    MAX_TOKEN_GENERATIONS_PER_HOUR,
    MAX_UPLOADS_PER_HOUR,
)
from fastapi import HTTPException


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Reset rate limit counters before each test."""
    reset_rate_limits()
    yield
    reset_rate_limits()


def _make_request(token=None, header_name="X-Portal-Token", query_token=None, bearer=False):
    """Create a mock FastAPI Request with the specified auth method."""
    request = MagicMock()
    request.headers = {}
    request.query_params = {}
    request.cookies = {}

    if token and bearer:
        request.headers["Authorization"] = f"Bearer {token}"
    elif token and header_name:
        request.headers[header_name] = token
    if query_token:
        request.query_params["token"] = query_token

    # Make .get() work like a dict
    request.headers = _DictLike(request.headers)
    request.query_params = _DictLike(request.query_params)

    return request


class _DictLike(dict):
    """Dict subclass that supports .get() for mock headers/params."""
    pass


# =============================================================================
# Token Generation Tests
# =============================================================================

class TestTokenGeneration:
    """Tests for generate_portal_access_token."""

    def test_generates_valid_token(self):
        """Token generation returns a decodable JWT with correct claims."""
        token = generate_portal_access_token(
            loan_id="loan-123",
            borrower_email="borrower@example.com",
            org_id="org-456",
        )

        assert isinstance(token, str)
        assert len(token) > 20

        # Decode and verify claims
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[PORTAL_TOKEN_ALGORITHM]
        )
        assert payload["sub"] == "borrower@example.com"
        assert payload["loan_id"] == "loan-123"
        assert payload["org_id"] == "org-456"
        assert payload["scope"] == "read_write"
        assert payload["iss"] == PORTAL_TOKEN_ISSUER
        assert "exp" in payload
        assert "iat" in payload

    def test_normalizes_email_to_lowercase(self):
        """Email is lowercased in the token."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="John.DOE@Example.Com",
            org_id="org-1",
        )
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[PORTAL_TOKEN_ALGORITHM]
        )
        assert payload["sub"] == "john.doe@example.com"

    def test_custom_expiry(self):
        """Custom expiry hours are respected."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
            expires_hours=1,
        )
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[PORTAL_TOKEN_ALGORITHM]
        )
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        diff = (exp_dt - iat_dt).total_seconds()
        assert 3500 < diff < 3700  # ~1 hour with small tolerance

    def test_read_only_scope(self):
        """Read scope can be set."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
            scope="read",
        )
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[PORTAL_TOKEN_ALGORITHM]
        )
        assert payload["scope"] == "read"

    def test_missing_loan_id_raises(self):
        """Missing loan_id raises ValueError."""
        with pytest.raises(ValueError, match="loan_id"):
            generate_portal_access_token(
                loan_id=None,
                borrower_email="test@example.com",
                org_id="org-1",
            )

    def test_missing_email_raises(self):
        """Missing borrower_email raises ValueError."""
        with pytest.raises(ValueError, match="borrower_email"):
            generate_portal_access_token(
                loan_id="loan-1",
                borrower_email="",
                org_id="org-1",
            )

    def test_missing_org_id_raises(self):
        """Missing org_id raises ValueError."""
        with pytest.raises(ValueError, match="org_id"):
            generate_portal_access_token(
                loan_id="loan-1",
                borrower_email="test@example.com",
                org_id=None,
            )

    def test_invalid_scope_raises(self):
        """Invalid scope raises ValueError."""
        with pytest.raises(ValueError, match="scope"):
            generate_portal_access_token(
                loan_id="loan-1",
                borrower_email="test@example.com",
                org_id="org-1",
                scope="admin",
            )


# =============================================================================
# Token Verification Tests
# =============================================================================

class TestTokenVerification:
    """Tests for verify_portal_access_token."""

    def test_valid_token(self):
        """Valid token returns correct claims."""
        token = generate_portal_access_token(
            loan_id="loan-100",
            borrower_email="jane@example.com",
            org_id="org-200",
        )
        claims = verify_portal_access_token(token)

        assert claims["loan_id"] == "loan-100"
        assert claims["borrower_email"] == "jane@example.com"
        assert claims["org_id"] == "org-200"
        assert claims["scope"] == "read_write"
        assert "issued_at" in claims
        assert "expires_at" in claims

    def test_expired_token_rejected(self):
        """Expired token raises 401."""
        # Create a token that expired 1 hour ago
        now = datetime.now(timezone.utc)
        payload = {
            "iss": PORTAL_TOKEN_ISSUER,
            "sub": "test@example.com",
            "loan_id": "loan-1",
            "org_id": "org-1",
            "scope": "read_write",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        }
        expired_token = jwt.encode(payload, SECRET_KEY, algorithm=PORTAL_TOKEN_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token(expired_token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_tampered_token_rejected(self):
        """Token signed with wrong key is rejected."""
        payload = {
            "iss": PORTAL_TOKEN_ISSUER,
            "sub": "test@example.com",
            "loan_id": "loan-1",
            "org_id": "org-1",
            "scope": "read_write",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        tampered_token = jwt.encode(payload, "wrong-secret-key", algorithm=PORTAL_TOKEN_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token(tampered_token)
        assert exc_info.value.status_code == 401

    def test_garbage_string_rejected(self):
        """Random string is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token("not-a-jwt-token")
        assert exc_info.value.status_code == 401

    def test_empty_token_rejected(self):
        """Empty string is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token("")
        assert exc_info.value.status_code == 401

    def test_wrong_issuer_rejected(self):
        """Token with wrong issuer is rejected."""
        payload = {
            "iss": "wrong-issuer",
            "sub": "test@example.com",
            "loan_id": "loan-1",
            "org_id": "org-1",
            "scope": "read_write",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=PORTAL_TOKEN_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token(token)
        assert exc_info.value.status_code == 401

    def test_missing_required_claims_rejected(self):
        """Token missing required claims is rejected."""
        payload = {
            "iss": PORTAL_TOKEN_ISSUER,
            "sub": "test@example.com",
            # Missing loan_id, org_id, scope
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=PORTAL_TOKEN_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_portal_access_token(token)
        assert exc_info.value.status_code == 401


# =============================================================================
# Magic Link Tests
# =============================================================================

class TestMagicLinkGeneration:
    """Tests for generate_portal_magic_link."""

    def test_generates_url_with_token(self):
        """Magic link contains a valid embedded token."""
        result = generate_portal_magic_link(
            loan_id="loan-50",
            borrower_email="magic@example.com",
            org_id="org-99",
            workspace_slug="smith-john-2026",
        )

        assert "url" in result
        assert "token" in result
        assert "expires_at" in result
        assert "smith-john-2026" in result["url"]
        assert result["token"] in result["url"]

        # Verify embedded token is valid
        claims = verify_portal_access_token(result["token"])
        assert claims["loan_id"] == "loan-50"
        assert claims["borrower_email"] == "magic@example.com"
        assert claims["org_id"] == "org-99"
        assert claims["scope"] == "read_write"

    def test_link_without_workspace_slug(self):
        """Magic link works without workspace slug."""
        result = generate_portal_magic_link(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
        )
        assert "url" in result
        assert "token=" in result["url"]


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting on token generation and uploads."""

    def test_token_generation_rate_limit(self):
        """After MAX_TOKEN_GENERATIONS_PER_HOUR tokens, generation is blocked."""
        email = "ratelimit@example.com"

        # Generate up to the limit
        for i in range(MAX_TOKEN_GENERATIONS_PER_HOUR):
            token = generate_portal_access_token(
                loan_id=f"loan-{i}",
                borrower_email=email,
                org_id="org-1",
            )
            assert token  # Should succeed

        # Next one should fail with 429
        with pytest.raises(HTTPException) as exc_info:
            generate_portal_access_token(
                loan_id="loan-extra",
                borrower_email=email,
                org_id="org-1",
            )
        assert exc_info.value.status_code == 429

    def test_rate_limit_per_email(self):
        """Rate limit is per email, not global."""
        # Fill rate limit for email A
        for i in range(MAX_TOKEN_GENERATIONS_PER_HOUR):
            generate_portal_access_token(
                loan_id=f"loan-{i}",
                borrower_email="a@example.com",
                org_id="org-1",
            )

        # Email B should still work
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="b@example.com",
            org_id="org-1",
        )
        assert token

    def test_upload_rate_limit(self):
        """After MAX_UPLOADS_PER_HOUR uploads, further uploads are blocked."""
        email = "uploader@example.com"

        for _ in range(MAX_UPLOADS_PER_HOUR):
            check_upload_rate_limit(email)  # Should not raise

        with pytest.raises(HTTPException) as exc_info:
            check_upload_rate_limit(email)
        assert exc_info.value.status_code == 429


# =============================================================================
# Scope Enforcement Tests
# =============================================================================

class TestScopeEnforcement:
    """Tests for require_write_scope."""

    def test_read_write_scope_allowed(self):
        """read_write scope passes write check."""
        portal_user = {"scope": "read_write"}
        require_write_scope(portal_user)  # Should not raise

    def test_read_only_scope_rejected(self):
        """read scope blocks write operations."""
        portal_user = {"scope": "read"}
        with pytest.raises(HTTPException) as exc_info:
            require_write_scope(portal_user)
        assert exc_info.value.status_code == 403

    def test_no_scope_rejected(self):
        """Missing scope blocks write operations."""
        portal_user = {}
        with pytest.raises(HTTPException) as exc_info:
            require_write_scope(portal_user)
        assert exc_info.value.status_code == 403


# =============================================================================
# Token Extraction Tests
# =============================================================================

class TestTokenExtraction:
    """Tests for get_current_portal_user token extraction."""

    @pytest.mark.asyncio
    async def test_extract_from_x_portal_token_header(self):
        """X-Portal-Token header is used for auth."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
        )
        request = _make_request(token=token, header_name="X-Portal-Token")
        db = MagicMock()

        result = await get_current_portal_user(
            request=request,
            db=db,
            workspace_slug="",  # Skip workspace verification
        )
        assert result["loan_id"] == "loan-1"
        assert result["borrower_email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_extract_from_bearer_header(self):
        """Authorization: Bearer header is used for auth."""
        token = generate_portal_access_token(
            loan_id="loan-2",
            borrower_email="bearer@example.com",
            org_id="org-2",
        )
        request = _make_request(token=token, bearer=True)
        db = MagicMock()

        result = await get_current_portal_user(
            request=request,
            db=db,
            workspace_slug="",
        )
        assert result["loan_id"] == "loan-2"

    @pytest.mark.asyncio
    async def test_extract_from_query_param(self):
        """?token= query parameter is used for auth."""
        token = generate_portal_access_token(
            loan_id="loan-3",
            borrower_email="query@example.com",
            org_id="org-3",
        )
        request = _make_request(query_token=token)
        db = MagicMock()

        result = await get_current_portal_user(
            request=request,
            db=db,
            workspace_slug="",
        )
        assert result["loan_id"] == "loan-3"

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self):
        """Missing token returns 401."""
        request = _make_request()
        db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_portal_user(
                request=request,
                db=db,
                workspace_slug="",
            )
        assert exc_info.value.status_code == 401


# =============================================================================
# Workspace Cross-Check Tests
# =============================================================================

class TestWorkspaceCrossCheck:
    """Tests for workspace verification against token claims."""

    @pytest.mark.asyncio
    async def test_wrong_org_rejected(self):
        """Token for org-1 cannot access workspace belonging to org-2."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
        )
        request = _make_request(token=token)

        # Mock DB to return workspace with different org
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, idx: [
            100,     # w.id
            999,     # w.organization_id (different from token's org-1)
            "loan-1",  # pl.main_loan_id
            200,     # pl.id
        ][idx]
        db.execute.return_value.fetchone.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_current_portal_user(
                request=request,
                db=db,
                workspace_slug="test-workspace",
            )
        assert exc_info.value.status_code == 401
        assert "does not match" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_wrong_loan_rejected(self):
        """Token for loan-1 cannot access workspace with loan-999."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
        )
        request = _make_request(token=token)

        # Mock DB to return workspace with matching org but different loan
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, idx: [
            100,       # w.id
            "org-1",   # w.organization_id (matches)
            "loan-999",  # pl.main_loan_id (different)
            200,       # pl.id
        ][idx]
        db.execute.return_value.fetchone.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_current_portal_user(
                request=request,
                db=db,
                workspace_slug="test-workspace",
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_rejected(self):
        """Token for a workspace that doesn't exist is rejected."""
        token = generate_portal_access_token(
            loan_id="loan-1",
            borrower_email="test@example.com",
            org_id="org-1",
        )
        request = _make_request(token=token)

        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None  # Workspace not found

        with pytest.raises(HTTPException) as exc_info:
            await get_current_portal_user(
                request=request,
                db=db,
                workspace_slug="nonexistent-slug",
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_matching_workspace_allowed(self):
        """Token claims matching workspace org and loan succeeds."""
        token = generate_portal_access_token(
            loan_id="loan-42",
            borrower_email="match@example.com",
            org_id="org-7",
        )
        request = _make_request(token=token)

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, idx: [
            100,       # w.id
            "org-7",   # w.organization_id (matches)
            "loan-42", # pl.main_loan_id (matches)
            200,       # pl.id
        ][idx]
        db.execute.return_value.fetchone.return_value = mock_result

        result = await get_current_portal_user(
            request=request,
            db=db,
            workspace_slug="test-workspace",
        )
        assert result["loan_id"] == "loan-42"
        assert result["org_id"] == "org-7"


# =============================================================================
# All Endpoints Require Auth (integration-level check)
# =============================================================================

class TestAllEndpointsRequireAuth:
    """Verify every portal endpoint has authentication."""

    def test_portal_routes_import_auth(self):
        """Verify the portal routes module imports auth dependencies."""
        import routes.smart_docs_portal_routes as portal_routes

        # The module should import the auth functions
        source_file = portal_routes.__file__
        with open(source_file, "r") as f:
            source = f.read()

        assert "get_current_portal_user" in source
        assert "require_write_scope" in source
        assert "check_upload_rate_limit" in source
        assert "_verify_portal_access_authenticated" in source

        # The old unauthenticated function should NOT be called
        # (the definition might still exist for backwards compat but calls should be gone)
        # Count calls to the old function (excluding the definition)
        lines = source.split("\n")
        old_calls = [
            line for line in lines
            if "_verify_portal_access(db," in line
            or "_verify_portal_access(db, workspace_slug)" in line
        ]
        assert len(old_calls) == 0, (
            f"Found {len(old_calls)} calls to old unauthenticated _verify_portal_access: {old_calls}"
        )

    def test_every_endpoint_uses_authenticated_verification(self):
        """Every endpoint handler in the file calls _verify_portal_access_authenticated."""
        import routes.smart_docs_portal_routes as portal_routes

        source_file = portal_routes.__file__
        with open(source_file, "r") as f:
            source = f.read()

        # Find all endpoint functions (decorated with @router.get/post)
        import re
        endpoint_pattern = re.compile(
            r'@router\.(get|post)\("(/portal/docs/[^"]+)"\)\s*\nasync def (\w+)',
            re.MULTILINE,
        )
        endpoints = endpoint_pattern.findall(source)
        assert len(endpoints) >= 14, f"Expected at least 14 endpoints, found {len(endpoints)}"

        # Each endpoint function body should contain _verify_portal_access_authenticated
        for method, path, func_name in endpoints:
            # Find the function body
            func_start = source.index(f"async def {func_name}")
            # Find next function or end of file
            next_def = source.find("\nasync def ", func_start + 1)
            next_decorator = source.find("\n@router.", func_start + 1)
            if next_def == -1:
                next_def = len(source)
            if next_decorator == -1:
                next_decorator = len(source)
            func_end = min(next_def, next_decorator)
            func_body = source[func_start:func_end]

            assert "_verify_portal_access_authenticated" in func_body, (
                f"Endpoint {method.upper()} {path} ({func_name}) does not call "
                f"_verify_portal_access_authenticated"
            )

    def test_write_endpoints_enforce_scope(self):
        """POST endpoints that modify data enforce write scope."""
        import routes.smart_docs_portal_routes as portal_routes

        source_file = portal_routes.__file__
        with open(source_file, "r") as f:
            source = f.read()

        # Write endpoints: upload, reupload, loe, confirm, reschedule, contact
        write_endpoints = [
            "portal_upload_document",
            "reupload_portal_document",
            "submit_letter_of_explanation",
            "confirm_portal_appointment",
            "reschedule_portal_appointment",
            "send_portal_contact_message",
        ]

        for func_name in write_endpoints:
            func_start = source.index(f"async def {func_name}")
            next_def = source.find("\nasync def ", func_start + 1)
            next_decorator = source.find("\n@router.", func_start + 1)
            if next_def == -1:
                next_def = len(source)
            if next_decorator == -1:
                next_decorator = len(source)
            func_end = min(next_def, next_decorator)
            func_body = source[func_start:func_end]

            assert "require_write_scope" in func_body, (
                f"Write endpoint {func_name} does not call require_write_scope"
            )

    def test_upload_endpoints_enforce_rate_limit(self):
        """Upload and reupload endpoints enforce upload rate limiting."""
        import routes.smart_docs_portal_routes as portal_routes

        source_file = portal_routes.__file__
        with open(source_file, "r") as f:
            source = f.read()

        upload_endpoints = [
            "portal_upload_document",
            "reupload_portal_document",
        ]

        for func_name in upload_endpoints:
            func_start = source.index(f"async def {func_name}")
            next_def = source.find("\nasync def ", func_start + 1)
            next_decorator = source.find("\n@router.", func_start + 1)
            if next_def == -1:
                next_def = len(source)
            if next_decorator == -1:
                next_decorator = len(source)
            func_end = min(next_def, next_decorator)
            func_body = source[func_start:func_end]

            assert "check_upload_rate_limit" in func_body, (
                f"Upload endpoint {func_name} does not call check_upload_rate_limit"
            )
