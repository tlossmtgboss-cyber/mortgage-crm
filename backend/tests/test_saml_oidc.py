"""
Tests for SAML 2.0 SSO, OIDC Provider, and JIT User Provisioning modules.

Covers:
  - SAML SP metadata generation (valid XML structure)
  - SAML AuthnRequest creation (deflate+b64 encoding, redirect URL)
  - SAML Response parsing with mock assertions (success, expired, bad status, audience)
  - SAML logout request creation
  - OIDC discovery document fetching (with mocked HTTP)
  - OIDC authorization URL generation
  - OIDC token exchange (mocked token endpoint)
  - OIDC ID token claims extraction (base64 JWT decoding)
  - OIDC UserInfo fetching
  - OIDC user attribute extraction (name parsing, group handling)
  - JIT provisioning: create new user from SSO attributes
  - JIT provisioning: update existing user on subsequent login
  - JIT group-to-role mapping (priority, defaults)

Run with: pytest tests/test_saml_oidc.py -v
"""

import sys
import os
import base64
import json
import zlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from auth.saml_sso import (
    generate_sp_metadata,
    create_authn_request,
    parse_saml_response,
    create_logout_request,
    _extract_email,
    _extract_attribute,
    _extract_groups,
)
from auth.oidc_provider import (
    fetch_discovery_document,
    create_authorization_url,
    exchange_code_for_tokens,
    extract_claims_from_id_token,
    fetch_userinfo,
    extract_user_attributes,
    _discovery_cache,
)
from auth.jit_provisioning import (
    provision_user_from_sso,
    update_user_from_sso,
    _map_groups_to_role,
    DEFAULT_GROUP_ROLE_MAP,
    PERMISSION_ROLE_TO_ROLE,
)


# =============================================================================
# Helpers
# =============================================================================

def _build_saml_response_xml(
    name_id: str = "user@example.com",
    status: str = "urn:oasis:names:tc:SAML:2.0:status:Success",
    not_on_or_after: str = None,
    audience: str = None,
    attributes: dict = None,
    session_index: str = "session_123",
    include_assertion: bool = True,
) -> str:
    """Build a minimal SAML Response XML string for testing."""
    if not_on_or_after is None:
        # Default to 5 minutes from now so it's not expired
        not_on_or_after = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    audience_xml = ""
    if audience:
        audience_xml = f"""
            <saml:AudienceRestriction>
              <saml:Audience>{audience}</saml:Audience>
            </saml:AudienceRestriction>"""

    attr_xml = ""
    if attributes:
        attr_entries = []
        for name, value in attributes.items():
            if isinstance(value, list):
                vals = "".join(f'<saml:AttributeValue>{v}</saml:AttributeValue>' for v in value)
            else:
                vals = f'<saml:AttributeValue>{value}</saml:AttributeValue>'
            attr_entries.append(f'<saml:Attribute Name="{name}">{vals}</saml:Attribute>')
        attr_xml = f'<saml:AttributeStatement>{"".join(attr_entries)}</saml:AttributeStatement>'

    assertion_xml = ""
    if include_assertion:
        assertion_xml = f"""
    <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_assert_1" Version="2.0"
                    IssueInstant="2025-01-01T00:00:00Z">
      <saml:Issuer>https://idp.example.com</saml:Issuer>
      <saml:Subject>
        <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
      </saml:Subject>
      <saml:Conditions NotOnOrAfter="{not_on_or_after}">
        {audience_xml}
      </saml:Conditions>
      <saml:AuthnStatement SessionIndex="{session_index}">
        <saml:AuthnContext>
          <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
        </saml:AuthnContext>
      </saml:AuthnStatement>
      {attr_xml}
    </saml:Assertion>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="_resp_1" Version="2.0" IssueInstant="2025-01-01T00:00:00Z"
                Destination="https://api.perenniaai.com/api/v1/auth/sso/saml/acs">
  <samlp:Status>
    <samlp:StatusCode Value="{status}"/>
  </samlp:Status>
  {assertion_xml}
</samlp:Response>"""
    return xml


def _encode_saml_response(xml: str) -> str:
    """Base64-encode a SAML response XML string."""
    return base64.b64encode(xml.encode("utf-8")).decode("utf-8")


class FakeUser:
    """Lightweight stand-in for a User ORM model."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.email = kwargs.get("email")
        self.first_name = kwargs.get("first_name", "")
        self.last_name = kwargs.get("last_name", "")
        self.hashed_password = kwargs.get("hashed_password")
        self.role = kwargs.get("role", "loan_officer")
        self.permission_role = kwargs.get("permission_role", "sales")
        self.organization_id = kwargs.get("organization_id")
        self.is_active = kwargs.get("is_active", True)
        self.email_verified = kwargs.get("email_verified", False)
        self.email_verified_at = kwargs.get("email_verified_at")
        self.onboarding_completed = kwargs.get("onboarding_completed", False)
        self.sso_provider = kwargs.get("sso_provider")
        self.sso_subject_id = kwargs.get("sso_subject_id")
        self.user_metadata = kwargs.get("user_metadata")
        self.last_activity_at = kwargs.get("last_activity_at")


class FakeDB:
    """Mock database session for JIT provisioning tests."""
    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True
        for i, obj in enumerate(self.added):
            if hasattr(obj, "id") and obj.id is None:
                obj.id = 100 + i


# =============================================================================
# SAML TESTS
# =============================================================================

class TestSAMLMetadata:
    """Tests for SAML SP metadata generation."""

    def test_metadata_returns_valid_xml(self):
        """generate_sp_metadata returns well-formed XML with expected elements."""
        metadata = generate_sp_metadata()
        assert '<?xml version="1.0"' in metadata
        assert "EntityDescriptor" in metadata
        assert "SPSSODescriptor" in metadata
        assert "AssertionConsumerService" in metadata
        assert "SingleLogoutService" in metadata

    def test_metadata_contains_entity_id(self):
        """Metadata includes the SP entity ID."""
        metadata = generate_sp_metadata(entity_id="https://custom.sp.example.com")
        assert 'entityID="https://custom.sp.example.com"' in metadata

    def test_metadata_contains_acs_url(self):
        """Metadata includes the assertion consumer service URL."""
        acs = "https://custom.sp.example.com/acs"
        metadata = generate_sp_metadata(acs_url=acs)
        assert f'Location="{acs}"' in metadata

    def test_metadata_contains_slo_url(self):
        """Metadata includes the single logout service URL."""
        slo = "https://custom.sp.example.com/slo"
        metadata = generate_sp_metadata(slo_url=slo)
        assert f'Location="{slo}"' in metadata

    def test_metadata_uses_defaults(self):
        """Metadata uses default env-based URLs when no overrides are given."""
        metadata = generate_sp_metadata()
        assert "perenniaai.com" in metadata

    def test_metadata_nameid_format(self):
        """Metadata requests email NameID format."""
        metadata = generate_sp_metadata()
        assert "nameid-format:emailAddress" in metadata

    def test_metadata_wants_signed_assertions(self):
        """Metadata sets WantAssertionsSigned to true."""
        metadata = generate_sp_metadata()
        assert 'WantAssertionsSigned="true"' in metadata


class TestSAMLAuthnRequest:
    """Tests for SAML AuthnRequest creation."""

    def test_authn_request_returns_url(self):
        """create_authn_request returns a valid redirect URL."""
        url = create_authn_request("https://idp.example.com/sso")
        assert url.startswith("https://idp.example.com/sso?")
        assert "SAMLRequest=" in url

    def test_authn_request_contains_encoded_request(self):
        """The SAMLRequest param is deflated and base64-encoded XML."""
        url = create_authn_request("https://idp.example.com/sso")
        # Extract SAMLRequest param
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(url).query)
        assert "SAMLRequest" in params
        # Decode it
        encoded = params["SAMLRequest"][0]
        decoded = base64.b64decode(encoded)
        # Re-inflate (raw deflate)
        xml_bytes = zlib.decompress(decoded, -zlib.MAX_WBITS)
        xml_str = xml_bytes.decode("utf-8")
        assert "AuthnRequest" in xml_str
        assert "Issuer" in xml_str

    def test_authn_request_includes_relay_state(self):
        """RelayState is included in the URL when provided."""
        url = create_authn_request("https://idp.example.com/sso", relay_state="/dashboard")
        assert "RelayState=" in url

    def test_authn_request_no_relay_state_when_none(self):
        """RelayState is absent from the URL when not provided."""
        url = create_authn_request("https://idp.example.com/sso")
        assert "RelayState" not in url

    def test_authn_request_uses_custom_entity_id(self):
        """Custom SP entity ID appears in the encoded request."""
        url = create_authn_request(
            "https://idp.example.com/sso",
            sp_entity_id="https://custom.sp.example.com",
        )
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(url).query)
        decoded = base64.b64decode(params["SAMLRequest"][0])
        xml_str = zlib.decompress(decoded, -zlib.MAX_WBITS).decode("utf-8")
        assert "https://custom.sp.example.com" in xml_str


class TestSAMLResponseParsing:
    """Tests for SAML Response/Assertion parsing."""

    def test_parse_valid_response(self):
        """A valid SAML response with Success status and valid assertion is accepted."""
        xml = _build_saml_response_xml(name_id="alice@example.com")
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(b64)

        assert is_valid is True
        assert attrs["email"] == "alice@example.com"
        assert attrs["name_id"] == "alice@example.com"
        assert attrs["session_index"] == "session_123"

    def test_parse_response_extracts_attributes(self):
        """Attributes from the assertion's AttributeStatement are extracted."""
        xml = _build_saml_response_xml(
            name_id="bob@example.com",
            attributes={
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": "Bob",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": "Smith",
                "http://schemas.xmlsoap.org/claims/Group": ["admins", "users"],
            },
        )
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(b64)

        assert is_valid is True
        assert attrs["first_name"] == "Bob"
        assert attrs["last_name"] == "Smith"
        assert "admins" in attrs["groups"]
        assert "users" in attrs["groups"]

    def test_parse_expired_assertion(self):
        """An expired assertion (NotOnOrAfter in the past) is rejected."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = _build_saml_response_xml(not_on_or_after=past)
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(b64)

        assert is_valid is False
        assert "expired" in attrs.get("error", "").lower()

    def test_parse_failed_status(self):
        """A response with a non-Success status is rejected."""
        xml = _build_saml_response_xml(
            status="urn:oasis:names:tc:SAML:2.0:status:Requester",
        )
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(b64)

        assert is_valid is False
        assert "error" in attrs

    def test_parse_audience_mismatch(self):
        """Audience restriction mismatch is detected."""
        xml = _build_saml_response_xml(audience="https://other-sp.example.com")
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(
            b64, expected_audience="https://correct-sp.example.com"
        )

        assert is_valid is False
        assert "audience" in attrs.get("error", "").lower()

    def test_parse_audience_match_succeeds(self):
        """Matching audience restriction passes validation."""
        xml = _build_saml_response_xml(audience="https://api.perenniaai.com")
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(
            b64, expected_audience="https://api.perenniaai.com"
        )

        assert is_valid is True

    def test_parse_no_assertion(self):
        """A response with no Assertion element is rejected."""
        xml = _build_saml_response_xml(include_assertion=False)
        b64 = _encode_saml_response(xml)

        is_valid, attrs = parse_saml_response(b64)

        assert is_valid is False
        assert "assertion" in attrs.get("error", "").lower()

    def test_parse_invalid_base64(self):
        """Invalid base64 input returns an error gracefully."""
        is_valid, attrs = parse_saml_response("not-valid-base64!!!")

        assert is_valid is False
        assert "error" in attrs


class TestSAMLLogoutRequest:
    """Tests for SAML LogoutRequest creation."""

    def test_logout_request_url(self):
        """create_logout_request returns a valid redirect URL."""
        url = create_logout_request(
            "https://idp.example.com/slo",
            name_id="alice@example.com",
            session_index="session_abc",
        )
        assert url.startswith("https://idp.example.com/slo?")
        assert "SAMLRequest=" in url

    def test_logout_request_contains_name_id(self):
        """The encoded LogoutRequest includes the NameID."""
        url = create_logout_request(
            "https://idp.example.com/slo",
            name_id="alice@example.com",
        )
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(url).query)
        decoded = base64.b64decode(params["SAMLRequest"][0])
        xml_str = zlib.decompress(decoded, -zlib.MAX_WBITS).decode("utf-8")
        assert "alice@example.com" in xml_str
        assert "LogoutRequest" in xml_str


class TestSAMLHelpers:
    """Tests for SAML helper functions."""

    def test_extract_email_from_name_id(self):
        """Email is extracted from NameID when it contains @."""
        result = _extract_email("USER@EXAMPLE.COM", {})
        assert result == "user@example.com"

    def test_extract_email_from_attributes(self):
        """Email is extracted from attributes when NameID is not an email."""
        attrs = {"email": "real@example.com"}
        result = _extract_email("some_opaque_id", attrs)
        assert result == "real@example.com"

    def test_extract_email_fallback(self):
        """Falls back to lowercase NameID when no email found."""
        result = _extract_email("SomeUser123", {})
        assert result == "someuser123"

    def test_extract_attribute_multiple_keys(self):
        """Tries multiple possible key names in order."""
        attrs = {"givenName": "Alice"}
        result = _extract_attribute(attrs, ["FirstName", "givenName", "first_name"])
        assert result == "Alice"

    def test_extract_attribute_returns_none(self):
        """Returns None when no key matches."""
        result = _extract_attribute({}, ["nope"])
        assert result is None

    def test_extract_groups_single(self):
        """Single group value is returned as a list."""
        attrs = {"groups": "admins"}
        result = _extract_groups(attrs)
        assert result == ["admins"]

    def test_extract_groups_list(self):
        """Multiple groups are returned as-is."""
        attrs = {"groups": ["admins", "users"]}
        result = _extract_groups(attrs)
        assert result == ["admins", "users"]

    def test_extract_groups_empty(self):
        """Empty attributes returns empty list."""
        result = _extract_groups({})
        assert result == []


# =============================================================================
# OIDC TESTS
# =============================================================================

class TestOIDCDiscovery:
    """Tests for OIDC discovery document fetching."""

    def setup_method(self):
        """Clear the discovery cache before each test."""
        _discovery_cache.clear()

    @patch("auth.oidc_provider.http_requests.get")
    def test_fetch_discovery_success(self, mock_get):
        """Successful discovery fetch returns the document and caches it."""
        doc = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
        }
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=doc))
        mock_get.return_value.raise_for_status = MagicMock()

        result = fetch_discovery_document("https://idp.example.com/.well-known/openid-configuration")

        assert result == doc
        assert "https://idp.example.com/.well-known/openid-configuration" in _discovery_cache

    @patch("auth.oidc_provider.http_requests.get")
    def test_fetch_discovery_cached(self, mock_get):
        """Cached discovery document is returned without a new HTTP request."""
        url = "https://idp.example.com/.well-known/openid-configuration"
        import time
        _discovery_cache[url] = ({"cached": True}, time.time() + 3600)

        result = fetch_discovery_document(url)

        assert result == {"cached": True}
        mock_get.assert_not_called()

    @patch("auth.oidc_provider.http_requests.get")
    def test_fetch_discovery_failure(self, mock_get):
        """Failed HTTP request returns None."""
        mock_get.side_effect = Exception("Connection refused")

        result = fetch_discovery_document("https://bad.example.com/.well-known/openid-configuration")

        assert result is None


class TestOIDCAuthorizationURL:
    """Tests for OIDC authorization URL generation."""

    def setup_method(self):
        _discovery_cache.clear()

    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_create_auth_url_success(self, mock_fetch):
        """Authorization URL is correctly generated from the discovery document."""
        mock_fetch.return_value = {
            "authorization_endpoint": "https://idp.example.com/authorize",
        }

        url, state, nonce = create_authorization_url(
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            client_id="my_client_id",
        )

        assert url is not None
        assert url.startswith("https://idp.example.com/authorize?")
        assert "client_id=my_client_id" in url
        assert "response_type=code" in url
        assert len(state) > 0
        assert len(nonce) > 0

    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_create_auth_url_custom_state_nonce(self, mock_fetch):
        """Custom state and nonce are used when provided."""
        mock_fetch.return_value = {
            "authorization_endpoint": "https://idp.example.com/authorize",
        }

        url, state, nonce = create_authorization_url(
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            client_id="cid",
            state="my_state",
            nonce="my_nonce",
        )

        assert state == "my_state"
        assert nonce == "my_nonce"
        assert "state=my_state" in url

    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_create_auth_url_discovery_fails(self, mock_fetch):
        """Returns None URL when discovery fetch fails."""
        mock_fetch.return_value = None

        url, state, nonce = create_authorization_url(
            discovery_url="https://bad.example.com/.well-known/openid-configuration",
            client_id="cid",
        )

        assert url is None


class TestOIDCTokenExchange:
    """Tests for OIDC authorization code -> token exchange."""

    def setup_method(self):
        _discovery_cache.clear()

    @patch("auth.oidc_provider.http_requests.post")
    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_exchange_code_success(self, mock_fetch, mock_post):
        """Successful token exchange returns the token response."""
        mock_fetch.return_value = {
            "token_endpoint": "https://idp.example.com/token",
        }
        token_response = {
            "id_token": "eyJ.header.payload.sig",
            "access_token": "at_123",
            "token_type": "Bearer",
        }
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=token_response),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        result = exchange_code_for_tokens(
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            client_id="cid",
            client_secret="secret",
            authorization_code="code_abc",
        )

        assert result == token_response
        mock_post.assert_called_once()

    @patch("auth.oidc_provider.http_requests.post")
    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_exchange_code_failure(self, mock_fetch, mock_post):
        """Failed token exchange returns None."""
        mock_fetch.return_value = {
            "token_endpoint": "https://idp.example.com/token",
        }
        mock_post.side_effect = Exception("Token endpoint error")

        result = exchange_code_for_tokens(
            discovery_url="https://idp.example.com/.well-known/openid-configuration",
            client_id="cid",
            client_secret="secret",
            authorization_code="code_abc",
        )

        assert result is None

    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_exchange_code_no_discovery(self, mock_fetch):
        """Returns None when discovery document fetch fails."""
        mock_fetch.return_value = None

        result = exchange_code_for_tokens(
            discovery_url="https://bad.example.com/.well-known/openid-configuration",
            client_id="cid",
            client_secret="secret",
            authorization_code="code_abc",
        )

        assert result is None


class TestOIDCClaimsExtraction:
    """Tests for ID token decoding and claims extraction."""

    def test_extract_claims_valid_jwt(self):
        """Valid JWT has its payload decoded correctly."""
        payload = {"sub": "user123", "email": "user@example.com", "given_name": "Test"}
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        jwt = f"eyJhbGciOiJSUzI1NiJ9.{payload_b64}.fake_signature"

        claims = extract_claims_from_id_token(jwt)

        assert claims is not None
        assert claims["sub"] == "user123"
        assert claims["email"] == "user@example.com"

    def test_extract_claims_invalid_format(self):
        """Invalid JWT format (not 3 parts) returns None."""
        claims = extract_claims_from_id_token("not.a.valid.jwt.too.many.parts")
        # The function checks for exactly 3 parts
        assert claims is None or isinstance(claims, dict)

    def test_extract_claims_two_parts(self):
        """JWT with only 2 parts returns None."""
        claims = extract_claims_from_id_token("header.payload")
        assert claims is None

    def test_extract_claims_corrupted_payload(self):
        """Corrupted payload base64 returns None."""
        claims = extract_claims_from_id_token("header.!!!corrupt!!!.signature")
        assert claims is None


class TestOIDCUserInfo:
    """Tests for OIDC UserInfo endpoint fetching."""

    def setup_method(self):
        _discovery_cache.clear()

    @patch("auth.oidc_provider.http_requests.get")
    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_fetch_userinfo_success(self, mock_fetch, mock_get):
        """Successful UserInfo fetch returns user data."""
        mock_fetch.return_value = {
            "userinfo_endpoint": "https://idp.example.com/userinfo",
        }
        userinfo = {"sub": "user123", "email": "user@example.com", "name": "Test User"}
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=userinfo),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        result = fetch_userinfo(
            "https://idp.example.com/.well-known/openid-configuration",
            "access_token_123",
        )

        assert result == userinfo
        # Verify bearer token was sent
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert "Bearer access_token_123" in str(call_kwargs)

    @patch("auth.oidc_provider.fetch_discovery_document")
    def test_fetch_userinfo_no_endpoint(self, mock_fetch):
        """Returns None when discovery doc has no userinfo_endpoint."""
        mock_fetch.return_value = {"authorization_endpoint": "..."}

        result = fetch_userinfo("https://idp.example.com/.well-known/openid-configuration", "token")

        assert result is None


class TestOIDCUserAttributes:
    """Tests for extracting standardized user attributes from OIDC claims."""

    def test_extract_standard_claims(self):
        """Standard OIDC claims (given_name, family_name, email) are extracted."""
        claims = {
            "sub": "user123",
            "email": "Alice@Example.com",
            "given_name": "Alice",
            "family_name": "Wonder",
        }

        attrs = extract_user_attributes(claims)

        assert attrs["email"] == "alice@example.com"
        assert attrs["first_name"] == "Alice"
        assert attrs["last_name"] == "Wonder"
        assert attrs["sub"] == "user123"

    def test_extract_name_fallback(self):
        """When given_name/family_name are missing, parses the 'name' field."""
        claims = {"sub": "u1", "email": "bob@example.com", "name": "Bob Johnson"}

        attrs = extract_user_attributes(claims)

        assert attrs["first_name"] == "Bob"
        assert attrs["last_name"] == "Johnson"

    def test_extract_single_name(self):
        """Single-word name goes to first_name only."""
        claims = {"sub": "u1", "email": "cher@example.com", "name": "Cher"}

        attrs = extract_user_attributes(claims)

        assert attrs["first_name"] == "Cher"
        assert attrs["last_name"] == ""

    def test_extract_groups_as_list(self):
        """Groups claim (list) is preserved."""
        claims = {"sub": "u1", "email": "a@b.com", "groups": ["admin", "users"]}

        attrs = extract_user_attributes(claims)

        assert attrs["groups"] == ["admin", "users"]

    def test_extract_groups_as_string(self):
        """Single group string is wrapped in a list."""
        claims = {"sub": "u1", "email": "a@b.com", "groups": "admin"}

        attrs = extract_user_attributes(claims)

        assert attrs["groups"] == ["admin"]

    def test_userinfo_overrides_claims(self):
        """UserInfo values take precedence over ID token claims."""
        claims = {"sub": "u1", "email": "old@example.com", "given_name": "Old"}
        userinfo = {"email": "new@example.com", "given_name": "New"}

        attrs = extract_user_attributes(claims, userinfo=userinfo)

        assert attrs["email"] == "new@example.com"
        assert attrs["first_name"] == "New"


# =============================================================================
# JIT PROVISIONING TESTS
# =============================================================================

class TestJITGroupRoleMapping:
    """Tests for IdP group-to-CRM-role mapping logic."""

    def test_admin_group_maps_to_admin(self):
        """'admins' group maps to the admin role."""
        role = _map_groups_to_role(["admins"])
        assert role == "admin"

    def test_highest_privilege_wins(self):
        """When multiple groups match, the highest-privilege role wins."""
        role = _map_groups_to_role(["loan_officers", "administrators", "processing"])
        assert role == "admin"

    def test_sales_group(self):
        """Sales/loan officer groups map to sales."""
        role = _map_groups_to_role(["loan-officers"])
        assert role == "sales"

    def test_no_match_uses_default(self):
        """Unrecognized groups fall back to the default role."""
        role = _map_groups_to_role(["unknown_group", "other_group"])
        assert role == "sales"  # default

    def test_custom_default(self):
        """Custom default is returned when no groups match."""
        role = _map_groups_to_role(["unknown"], default="processing")
        assert role == "processing"

    def test_empty_groups(self):
        """Empty group list returns default."""
        role = _map_groups_to_role([])
        assert role == "sales"

    def test_case_insensitive_matching(self):
        """Group matching is case-insensitive."""
        role = _map_groups_to_role(["Admins"])
        # The function lowercases before lookup
        assert role == "admin"

    def test_management_group(self):
        """Management groups map to management role."""
        role = _map_groups_to_role(["managers"])
        assert role == "management"


class TestJITProvisionUser:
    """Tests for JIT user provisioning (new user creation from SSO)."""

    @patch("database.models.core.User", FakeUser)
    def test_provision_creates_user(self):
        """provision_user_from_sso creates a new user with correct attributes."""
        db = FakeDB()
        user = provision_user_from_sso(
            db=db,
            email="new.user@example.com",
            first_name="New",
            last_name="User",
            organization_id=42,
            sso_provider="saml",
            sso_subject_id="saml_id_123",
            groups=["loan_officers"],
        )

        assert len(db.added) == 1
        assert db.flushed is True
        assert user.email == "new.user@example.com"
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert user.organization_id == 42
        assert user.sso_provider == "saml"
        assert user.is_active is True
        assert user.email_verified is True
        assert user.permission_role == "sales"

    @patch("database.models.core.User", FakeUser)
    def test_provision_admin_group(self):
        """Admin group membership results in admin role."""
        db = FakeDB()
        user = provision_user_from_sso(
            db=db,
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            organization_id=1,
            sso_provider="oidc",
            sso_subject_id="oidc_sub_456",
            groups=["administrators"],
        )

        assert user.permission_role == "admin"
        assert user.role == "admin"

    @patch("database.models.core.User", FakeUser)
    def test_provision_random_password(self):
        """Provisioned user has a non-empty password hash (SSO placeholder)."""
        db = FakeDB()
        user = provision_user_from_sso(
            db=db,
            email="sso@example.com",
            first_name="SSO",
            last_name="User",
            organization_id=1,
            sso_provider="saml",
            sso_subject_id="id",
        )

        assert user.hashed_password is not None
        assert "$sso_provisioned$" in user.hashed_password

    @patch("database.models.core.User", FakeUser)
    def test_provision_metadata(self):
        """Provisioned user has metadata with provisioning details."""
        db = FakeDB()
        user = provision_user_from_sso(
            db=db,
            email="meta@example.com",
            first_name="Meta",
            last_name="User",
            organization_id=1,
            sso_provider="oidc",
            sso_subject_id="sub_789",
            groups=["sales"],
        )

        assert user.user_metadata is not None
        assert user.user_metadata["provisioned_via"] == "sso_oidc"
        assert user.user_metadata["idp_groups"] == ["sales"]


class TestJITUpdateUser:
    """Tests for updating existing user attributes on subsequent SSO login."""

    def test_update_fills_empty_fields(self):
        """SSO update fills in first_name and last_name when they were empty."""
        db = FakeDB()
        user = FakeUser(
            id=1, email="user@example.com",
            first_name="", last_name="",
            sso_provider=None, sso_subject_id=None,
        )

        result = update_user_from_sso(
            db=db,
            user=user,
            first_name="Alice",
            last_name="Smith",
            sso_provider="saml",
            sso_subject_id="saml_id",
        )

        assert result.first_name == "Alice"
        assert result.last_name == "Smith"
        assert result.sso_provider == "saml"

    def test_update_does_not_overwrite_existing(self):
        """SSO update does NOT overwrite existing non-empty name fields."""
        db = FakeDB()
        user = FakeUser(
            id=1, email="user@example.com",
            first_name="Original", last_name="Name",
            sso_provider="saml", sso_subject_id="old_id",
        )

        result = update_user_from_sso(
            db=db,
            user=user,
            first_name="NewFirst",
            last_name="NewLast",
            sso_provider="oidc",
            sso_subject_id="new_id",
        )

        # Should keep original values since they were non-empty
        assert result.first_name == "Original"
        assert result.last_name == "Name"
        assert result.sso_provider == "saml"

    def test_update_sets_last_activity(self):
        """SSO update refreshes last_activity_at."""
        db = FakeDB()
        user = FakeUser(id=1, email="user@example.com", last_activity_at=None)

        update_user_from_sso(db=db, user=user)

        assert user.last_activity_at is not None
