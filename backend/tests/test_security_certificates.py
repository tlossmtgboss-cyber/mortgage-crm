"""
Tests for certificate pinning endpoints.

Covers:
- GET  /api/v1/security/certificate-pins  (unauthenticated, returns SPKI hashes)
- POST /api/v1/security/pin-failure       (accepts failure reports, rate-limited)
- _der_cert_to_spki_hash and _parse_der_tlv internal helpers
- verify_certificate_pins (mocked network)
"""

import pytest
import time
import base64
import hashlib
from unittest.mock import patch
from fastapi.testclient import TestClient

from routes.security_certificate_routes import _rate_limit_buckets


@pytest.fixture(autouse=True)
def _clear_rate_limit_state():
    """Reset the in-memory rate-limit buckets between tests."""
    _rate_limit_buckets.clear()
    yield
    _rate_limit_buckets.clear()


# =============================================================================
# GET /api/v1/security/certificate-pins
# =============================================================================


class TestGetCertificatePins:
    """Tests for the certificate pins retrieval endpoint."""

    def test_get_certificate_pins_no_auth_required(self, client):
        """Endpoint returns 200 without any auth headers."""
        resp = client.get("/api/v1/security/certificate-pins")
        assert resp.status_code == 200

    def test_get_certificate_pins_returns_domains(self, client):
        """Response contains keys for both production domains."""
        resp = client.get("/api/v1/security/certificate-pins")
        data = resp.json()
        assert "api.perenniaai.com" in data
        assert "app.perenniaai.com" in data

    def test_get_certificate_pins_has_spki_hashes(self, client):
        """Each domain entry has an spkiHashes array with at least 3 pins."""
        resp = client.get("/api/v1/security/certificate-pins")
        data = resp.json()
        for domain in ("api.perenniaai.com", "app.perenniaai.com"):
            hashes = data[domain]["spkiHashes"]
            assert isinstance(hashes, list)
            assert len(hashes) >= 3
            # Each hash should be a non-empty base64 string ending with '='
            for h in hashes:
                assert isinstance(h, str)
                assert len(h) > 0
                assert h.endswith("=")

    def test_get_certificate_pins_response_shape(self, client):
        """Each domain entry has includeSubdomains (bool) and notAfter fields."""
        resp = client.get("/api/v1/security/certificate-pins")
        data = resp.json()
        for domain in ("api.perenniaai.com", "app.perenniaai.com"):
            entry = data[domain]
            assert "includeSubdomains" in entry
            assert isinstance(entry["includeSubdomains"], bool)
            assert "notAfter" in entry
            # notAfter is either a string or null
            assert entry["notAfter"] is None or isinstance(entry["notAfter"], str)


# =============================================================================
# POST /api/v1/security/pin-failure
# =============================================================================


class TestPinFailureReport:
    """Tests for the pin failure reporting endpoint."""

    def _valid_report_payload(self):
        """Return a minimal valid PinFailureRequest body."""
        return {
            "reports": [
                {
                    "domain": "api.perenniaai.com",
                    "reason": "pin_mismatch",
                    "receivedHashes": ["abc123="],
                    "timestamp": "2026-04-10T12:00:00Z",
                    "platform": "iOS",
                    "appVersion": "1.0.0",
                }
            ],
            "deviceInfo": {
                "platform": "iOS",
                "isNative": True,
                "osVersion": "19.0",
                "model": "iPhone16,1",
            },
        }

    def test_pin_failure_accepts_report(self, client):
        """A valid pin failure report returns 200 with success=True."""
        resp = client.post(
            "/api/v1/security/pin-failure",
            json=self._valid_report_payload(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "1" in body["message"]  # "Received 1 pin failure report(s)"

    def test_pin_failure_rate_limited(self, client):
        """More than 20 reports from the same IP within 60s triggers 429."""
        payload = self._valid_report_payload()

        # First 20 requests should succeed
        for i in range(20):
            resp = client.post("/api/v1/security/pin-failure", json=payload)
            assert resp.status_code == 200, f"Request {i+1} failed unexpectedly"

        # 21st request should be rate-limited
        resp = client.post("/api/v1/security/pin-failure", json=payload)
        assert resp.status_code == 429
        assert "Too many" in resp.json()["detail"]

    def test_pin_failure_validates_input(self, client):
        """Missing required fields return 422 Unprocessable Entity."""
        # Empty body
        resp = client.post("/api/v1/security/pin-failure", json={})
        assert resp.status_code == 422

        # reports present but empty list (min_length=1)
        resp = client.post(
            "/api/v1/security/pin-failure",
            json={"reports": []},
        )
        assert resp.status_code == 422

        # Report missing required 'domain' field
        resp = client.post(
            "/api/v1/security/pin-failure",
            json={"reports": [{"reason": "pin_mismatch"}]},
        )
        assert resp.status_code == 422

        # Report missing required 'reason' field
        resp = client.post(
            "/api/v1/security/pin-failure",
            json={"reports": [{"domain": "api.perenniaai.com"}]},
        )
        assert resp.status_code == 422

    def test_pin_failure_multiple_reports(self, client):
        """Multiple reports in a single request are accepted."""
        payload = {
            "reports": [
                {"domain": "api.perenniaai.com", "reason": "pin_mismatch"},
                {"domain": "app.perenniaai.com", "reason": "certificate_expired"},
            ],
        }
        resp = client.post("/api/v1/security/pin-failure", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "2" in body["message"]

    def test_pin_failure_minimal_report(self, client):
        """Report with only required fields (domain, reason) succeeds."""
        payload = {
            "reports": [
                {"domain": "api.perenniaai.com", "reason": "test"},
            ],
        }
        resp = client.post("/api/v1/security/pin-failure", json=payload)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# =============================================================================
# SPKI HASH VALIDATION
# =============================================================================


class TestSpkiHashFormat:
    """Validate the base64 SPKI hashes are properly formatted SHA-256."""

    def test_spki_hashes_are_valid_base64_sha256(self, client):
        """All SPKI hashes decode to exactly 32 bytes (SHA-256 digest size)."""
        resp = client.get("/api/v1/security/certificate-pins")
        data = resp.json()

        for domain, config in data.items():
            for h in config["spkiHashes"]:
                try:
                    decoded = base64.b64decode(h)
                    assert len(decoded) == 32, (
                        f"Hash for {domain} decoded to {len(decoded)} bytes, expected 32"
                    )
                except Exception as exc:
                    pytest.fail(f"Invalid base64 hash '{h}' for {domain}: {exc}")


# =============================================================================
# _check_rate_limit DIRECT TESTS
# =============================================================================


class TestCheckRateLimit:
    """Test the _check_rate_limit function directly."""

    def test_allows_within_limit(self):
        """Requests within _rate_limit_max are allowed."""
        from routes.security_certificate_routes import (
            _check_rate_limit,
            _rate_limit_max,
        )

        test_ip = "10.0.0.100"
        for _ in range(_rate_limit_max):
            assert _check_rate_limit(test_ip) is True

    def test_blocks_when_exceeded(self):
        """Request after _rate_limit_max are blocked."""
        from routes.security_certificate_routes import (
            _check_rate_limit,
            _rate_limit_max,
        )

        test_ip = "10.0.0.101"
        for _ in range(_rate_limit_max):
            _check_rate_limit(test_ip)
        assert _check_rate_limit(test_ip) is False

    def test_resets_after_window_expires(self):
        """Old entries outside the window are pruned, allowing new requests."""
        from routes.security_certificate_routes import (
            _check_rate_limit,
            _rate_limit_max,
            _rate_limit_window,
        )

        test_ip = "10.0.0.102"
        # Simulate entries that are older than the window
        past = time.time() - _rate_limit_window - 1
        _rate_limit_buckets[test_ip] = [past] * _rate_limit_max

        # Should be allowed because old entries are pruned
        assert _check_rate_limit(test_ip) is True

    def test_different_ips_are_independent(self):
        """Rate limits are tracked per IP independently."""
        from routes.security_certificate_routes import (
            _check_rate_limit,
            _rate_limit_max,
        )

        ip_a = "10.0.0.200"
        ip_b = "10.0.0.201"

        # Exhaust IP A
        for _ in range(_rate_limit_max):
            _check_rate_limit(ip_a)
        assert _check_rate_limit(ip_a) is False

        # IP B should still be allowed
        assert _check_rate_limit(ip_b) is True


# =============================================================================
# _parse_der_tlv TESTS
# =============================================================================


class TestParseDerTlv:
    """Test the minimal ASN.1 DER TLV parser."""

    def test_parse_simple_integer(self):
        """Parse a short-form DER INTEGER: tag=0x02, len=1, value=0x05."""
        from routes.security_certificate_routes import _parse_der_tlv

        data = bytes([0x02, 0x01, 0x05])  # INTEGER, length 1, value 5
        tag, total_len, value = _parse_der_tlv(data, 0)

        assert tag == 0x02
        assert total_len == 3  # tag(1) + len(1) + value(1)
        assert value == bytes([0x05])

    def test_parse_sequence(self):
        """Parse a SEQUENCE wrapping an INTEGER."""
        from routes.security_certificate_routes import _parse_der_tlv

        inner = bytes([0x02, 0x01, 0x05])
        data = bytes([0x30, len(inner)]) + inner

        tag, total_len, value = _parse_der_tlv(data, 0)

        assert tag == 0x30
        assert total_len == 2 + len(inner)
        assert value == inner

    def test_parse_long_form_length(self):
        """Parse DER with multi-byte (long-form) length encoding."""
        from routes.security_certificate_routes import _parse_der_tlv

        length = 128
        value_bytes = bytes([0xAA] * length)
        data = bytes([0x04, 0x81, length]) + value_bytes

        tag, total_len, value = _parse_der_tlv(data, 0)

        assert tag == 0x04
        assert total_len == 3 + length  # tag(1) + 0x81(1) + len_byte(1) + value(128)
        assert len(value) == length

    def test_parse_at_offset(self):
        """Parse starting at a non-zero offset."""
        from routes.security_certificate_routes import _parse_der_tlv

        pad = bytes([0xFF] * 5)
        tlv = bytes([0x02, 0x01, 0x42])
        data = pad + tlv

        tag, total_len, value = _parse_der_tlv(data, 5)

        assert tag == 0x02
        assert value == bytes([0x42])

    def test_raises_on_offset_past_end(self):
        """Parsing past the end of data raises ValueError."""
        from routes.security_certificate_routes import _parse_der_tlv

        data = bytes([0x02, 0x01, 0x05])
        with pytest.raises(ValueError, match="Offset past end"):
            _parse_der_tlv(data, 10)

    def test_raises_on_indefinite_length(self):
        """Indefinite length (0x80) raises ValueError."""
        from routes.security_certificate_routes import _parse_der_tlv

        data = bytes([0x30, 0x80])
        with pytest.raises(ValueError, match="Indefinite length"):
            _parse_der_tlv(data, 0)

    def test_parse_zero_length_value(self):
        """Parse a TLV with zero-length value."""
        from routes.security_certificate_routes import _parse_der_tlv

        data = bytes([0x05, 0x00])  # NULL tag, length 0
        tag, total_len, value = _parse_der_tlv(data, 0)

        assert tag == 0x05
        assert total_len == 2
        assert value == b""


# =============================================================================
# _der_cert_to_spki_hash TESTS
# =============================================================================


class TestDerCertToSpkiHash:
    """Test SPKI hash extraction from DER certificates."""

    def test_returns_none_for_non_sequence(self):
        """Non-SEQUENCE outer tag returns None."""
        from routes.security_certificate_routes import _der_cert_to_spki_hash

        data = bytes([0x02, 0x01, 0x05])  # INTEGER, not SEQUENCE
        result = _der_cert_to_spki_hash(data)
        assert result is None

    def test_returns_none_for_empty_data(self):
        """Empty bytes returns None."""
        from routes.security_certificate_routes import _der_cert_to_spki_hash

        result = _der_cert_to_spki_hash(b"")
        assert result is None

    def test_returns_none_for_truncated_data(self):
        """Truncated DER data returns None gracefully (no exception)."""
        from routes.security_certificate_routes import _der_cert_to_spki_hash

        data = bytes([0x30, 0x03, 0x30, 0x01, 0x00])
        result = _der_cert_to_spki_hash(data)
        assert result is None

    def test_extracts_hash_from_mock_certificate(self):
        """Given a well-formed mock certificate DER, returns valid base64 SHA-256."""
        from routes.security_certificate_routes import _der_cert_to_spki_hash

        def make_tlv(tag, value):
            length = len(value)
            if length < 128:
                return bytes([tag, length]) + value
            length_bytes = length.to_bytes((length.bit_length() + 7) // 8, "big")
            return bytes([tag, 0x80 | len(length_bytes)]) + length_bytes + value

        # Build TBSCertificate with 7 fields (index 0=version, 1-5=dummies, 6=SPKI)
        version = make_tlv(0xA0, make_tlv(0x02, bytes([0x02])))  # v3
        dummy_fields = b""
        for _ in range(5):
            dummy_fields += make_tlv(0x30, bytes([0x00]))

        spki_content = bytes([0x01, 0x02, 0x03, 0x04])
        spki = make_tlv(0x30, spki_content)

        tbs = make_tlv(0x30, version + dummy_fields + spki)
        sig_alg = make_tlv(0x30, bytes([0x00]))
        sig = make_tlv(0x03, bytes([0x00]))
        cert = make_tlv(0x30, tbs + sig_alg + sig)

        result = _der_cert_to_spki_hash(cert)
        assert result is not None

        # Verify valid base64 -> 32 bytes (SHA-256)
        decoded = base64.b64decode(result)
        assert len(decoded) == 32

        # Verify the hash matches SHA-256 of the raw SPKI DER
        expected = base64.b64encode(hashlib.sha256(spki).digest()).decode("ascii")
        assert result == expected


# =============================================================================
# verify_certificate_pins TESTS (mocked network)
# =============================================================================


class TestVerifyCertificatePins:
    """Test verify_certificate_pins with mocked TLS connections."""

    def test_returns_expected_structure(self):
        """Result contains last_checked, domains, all_match."""
        from routes.security_certificate_routes import verify_certificate_pins

        with patch(
            "routes.security_certificate_routes._extract_spki_hashes",
            return_value=[],
        ):
            result = verify_certificate_pins()

        assert "last_checked" in result
        assert "domains" in result
        assert "all_match" in result
        assert isinstance(result["domains"], dict)

    def test_reports_mismatch_when_no_hashes_extracted(self):
        """Empty hash list means match=False for all domains."""
        from routes.security_certificate_routes import verify_certificate_pins

        with patch(
            "routes.security_certificate_routes._extract_spki_hashes",
            return_value=[],
        ):
            result = verify_certificate_pins()

        assert result["all_match"] is False
        for domain, info in result["domains"].items():
            assert info["match"] is False

    def test_reports_match_when_hash_overlaps(self):
        """When a live hash matches a configured hash, domain shows match=True."""
        from routes.security_certificate_routes import (
            verify_certificate_pins,
            CERTIFICATE_PINS,
        )

        # Use the first configured hash for api.perenniaai.com
        api_hash = CERTIFICATE_PINS["api.perenniaai.com"]["spkiHashes"][0]

        with patch(
            "routes.security_certificate_routes._extract_spki_hashes",
            return_value=[api_hash],
        ):
            result = verify_certificate_pins()

        assert result["domains"]["api.perenniaai.com"]["match"] is True

    def test_stores_last_verification(self):
        """verify_certificate_pins updates the module-level _last_verification."""
        from routes import security_certificate_routes
        security_certificate_routes._last_verification = None

        with patch(
            "routes.security_certificate_routes._extract_spki_hashes",
            return_value=[],
        ):
            security_certificate_routes.verify_certificate_pins()

        assert security_certificate_routes._last_verification is not None
        assert "last_checked" in security_certificate_routes._last_verification
