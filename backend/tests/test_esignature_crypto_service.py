"""
Test E-Signature Cryptographic Service

Comprehensive tests for the built-in e-signature crypto operations:
- SHA-256 document hashing (determinism, edge cases)
- HMAC signature generation and verification
- Signing token creation with expiration
- Signing token validation (valid, expired, tampered, wrong recipient/envelope)
- Completion certificate generation with signer info
- Tamper detection on modified documents
- Hash consistency across multiple calls
- Token payload encoding/decoding round-trip
- Key derivation isolation across different service instances
- Edge cases (empty document, large content, unicode)
- Certificate format validation
- Signature chain / audit trail integrity
- Access code generation and verification
- Signing payload creation
"""

import base64
import hashlib
import hmac as hmac_mod
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from services.smart_docs.esignature_crypto_service import (
    ESignatureCryptoService,
    SigningCertificate,
    get_esignature_crypto_service,
)
from services.smart_docs.esignature_key_manager import (
    ESignatureKeyManager,
    reset_key_manager,
)


# =============================================================================
# Fixtures
# =============================================================================

# Secrets must be >= 32 chars for the new key manager validation.
_TEST_SIGNING_SECRET = "test-signing-secret-32-bytes-ok!"
_TEST_TOKEN_SECRET = "test-token-secret-32-bytes-okay!"


@pytest.fixture(autouse=True)
def _reset_key_manager_singleton():
    """Reset the key manager singleton before and after each test."""
    reset_key_manager()
    yield
    reset_key_manager()


@pytest.fixture
def crypto_service():
    """Create a fresh ESignatureCryptoService with deterministic secrets."""
    km = ESignatureKeyManager(
        signing_secret=_TEST_SIGNING_SECRET,
        token_secret=_TEST_TOKEN_SECRET,
    )
    svc = ESignatureCryptoService(key_manager=km)
    svc._base_url = "https://test.example.com/verify"
    return svc


@pytest.fixture
def sample_document_content():
    """Sample PDF-like bytes for hashing tests."""
    return b"%PDF-1.4 sample document content for testing purposes"


@pytest.fixture
def sample_signer_info():
    """Standard signer info dict."""
    return {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "signed_at": "2026-03-10T14:30:00+00:00",
    }


@pytest.fixture
def sample_envelope_uuid():
    """A stable envelope UUID for tests."""
    return "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


# =============================================================================
# 1. SHA-256 Document Hashing
# =============================================================================

@pytest.mark.unit
class TestDocumentHashing:
    """Tests for hash_document: SHA-256 determinism and edge cases."""

    def test_hash_document_returns_sha256_hex(self, crypto_service, sample_document_content):
        """hash_document should return a 64-char lowercase hex SHA-256 digest."""
        result = crypto_service.hash_document(sample_document_content)

        assert isinstance(result, str)
        assert len(result) == 64
        # Verify it is valid hex
        int(result, 16)
        assert result == result.lower()

    def test_hash_document_deterministic(self, crypto_service, sample_document_content):
        """Hashing the same content twice must yield the same result."""
        hash1 = crypto_service.hash_document(sample_document_content)
        hash2 = crypto_service.hash_document(sample_document_content)
        assert hash1 == hash2

    def test_hash_document_matches_stdlib(self, crypto_service, sample_document_content):
        """Result must match Python's hashlib.sha256 directly."""
        expected = hashlib.sha256(sample_document_content).hexdigest()
        result = crypto_service.hash_document(sample_document_content)
        assert result == expected

    def test_hash_document_empty_bytes(self, crypto_service):
        """Hashing empty bytes should return the SHA-256 of empty input."""
        result = crypto_service.hash_document(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected
        # SHA-256 of empty string is well-known
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_hash_document_different_content_different_hash(self, crypto_service):
        """Different content must produce different hashes."""
        hash1 = crypto_service.hash_document(b"document version 1")
        hash2 = crypto_service.hash_document(b"document version 2")
        assert hash1 != hash2

    def test_hash_document_unicode_content(self, crypto_service):
        """Unicode content encoded as bytes should hash correctly."""
        content = "Mortgage for Rene Dupont - 500,000 EUR".encode("utf-8")
        result = crypto_service.hash_document(content)
        assert len(result) == 64

    def test_hash_document_large_content(self, crypto_service):
        """Hashing a large document (10 MB) should succeed."""
        large_content = b"X" * (10 * 1024 * 1024)
        result = crypto_service.hash_document(large_content)
        assert len(result) == 64
        # Verify it is deterministic even for large content
        assert result == crypto_service.hash_document(large_content)

    def test_hash_document_binary_content(self, crypto_service):
        """Hashing raw binary (all byte values) should work."""
        content = bytes(range(256))
        result = crypto_service.hash_document(content)
        assert len(result) == 64


# =============================================================================
# 2. HMAC Signature Generation and Verification
# =============================================================================

@pytest.mark.unit
class TestSignatureHashGeneration:
    """Tests for generate_signature_hash and verify_signature_hash."""

    def test_generate_signature_hash_returns_hex(self, crypto_service):
        """Signature hash should be a 64-char hex string."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        result = crypto_service.generate_signature_hash(
            document_hash="abc123" * 10 + "abcd",
            signer_email="signer@example.com",
            signed_at=signed_at,
            ip_address="10.0.0.1",
        )
        assert isinstance(result, str)
        assert len(result) == 64
        int(result, 16)

    def test_generate_signature_hash_deterministic(self, crypto_service):
        """Same inputs must produce the same signature hash."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        kwargs = dict(
            document_hash="d0c1234abcdef" * 5 + "ab",
            signer_email="test@example.com",
            signed_at=signed_at,
            ip_address="10.0.0.1",
        )
        hash1 = crypto_service.generate_signature_hash(**kwargs)
        hash2 = crypto_service.generate_signature_hash(**kwargs)
        assert hash1 == hash2

    def test_verify_signature_hash_valid(self, crypto_service):
        """verify_signature_hash should return True for a correctly generated hash."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        doc_hash = "a" * 64
        email = "signer@example.com"
        ip = "192.168.1.1"

        sig_hash = crypto_service.generate_signature_hash(doc_hash, email, signed_at, ip)
        assert crypto_service.verify_signature_hash(sig_hash, doc_hash, email, signed_at, ip) is True

    def test_verify_signature_hash_wrong_doc_hash(self, crypto_service):
        """Verification should fail if the document hash changed."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        sig_hash = crypto_service.generate_signature_hash("a" * 64, "s@e.com", signed_at, "1.2.3.4")
        assert crypto_service.verify_signature_hash(sig_hash, "b" * 64, "s@e.com", signed_at, "1.2.3.4") is False

    def test_verify_signature_hash_wrong_email(self, crypto_service):
        """Verification should fail if the signer email changed."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        doc_hash = "c" * 64
        sig_hash = crypto_service.generate_signature_hash(doc_hash, "real@example.com", signed_at, "1.2.3.4")
        assert crypto_service.verify_signature_hash(sig_hash, doc_hash, "fake@example.com", signed_at, "1.2.3.4") is False

    def test_verify_signature_hash_wrong_ip(self, crypto_service):
        """Verification should fail if the IP address changed."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        doc_hash = "d" * 64
        email = "user@example.com"
        sig_hash = crypto_service.generate_signature_hash(doc_hash, email, signed_at, "10.0.0.1")
        assert crypto_service.verify_signature_hash(sig_hash, doc_hash, email, signed_at, "10.0.0.2") is False

    def test_verify_signature_hash_wrong_timestamp(self, crypto_service):
        """Verification should fail if the timestamp changed."""
        signed_at_real = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        signed_at_fake = datetime(2026, 3, 10, 14, 31, 0, tzinfo=timezone.utc)
        doc_hash = "e" * 64
        sig_hash = crypto_service.generate_signature_hash(doc_hash, "u@e.com", signed_at_real, "1.1.1.1")
        assert crypto_service.verify_signature_hash(sig_hash, doc_hash, "u@e.com", signed_at_fake, "1.1.1.1") is False

    def test_signature_email_normalization(self, crypto_service):
        """Email should be lowercased and stripped before hashing."""
        signed_at = datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc)
        doc_hash = "f" * 64
        ip = "1.2.3.4"
        hash_lower = crypto_service.generate_signature_hash(doc_hash, "user@example.com", signed_at, ip)
        hash_upper = crypto_service.generate_signature_hash(doc_hash, "  USER@EXAMPLE.COM  ", signed_at, ip)
        assert hash_lower == hash_upper


# =============================================================================
# 3-4. Signing Token Creation and Validation
# =============================================================================

@pytest.mark.unit
class TestSigningTokens:
    """Tests for generate_signing_token and validate_signing_token."""

    def test_generate_signing_token_returns_tuple(self, crypto_service, sample_envelope_uuid):
        """Should return (token_string, expiry_datetime)."""
        token, expires_at = crypto_service.generate_signing_token(
            recipient_id=42,
            envelope_uuid=sample_envelope_uuid,
        )
        assert isinstance(token, str)
        assert isinstance(expires_at, datetime)
        assert len(token) > 0

    def test_generate_signing_token_default_expiry(self, crypto_service, sample_envelope_uuid):
        """Default expiry should be ~168 hours (7 days) from now."""
        before = datetime.now(timezone.utc)
        _, expires_at = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(hours=167, minutes=59)
        expected_max = after + timedelta(hours=168, minutes=1)
        assert expected_min <= expires_at <= expected_max

    def test_generate_signing_token_custom_expiry(self, crypto_service, sample_envelope_uuid):
        """Custom expiry hours should be respected."""
        before = datetime.now(timezone.utc)
        _, expires_at = crypto_service.generate_signing_token(42, sample_envelope_uuid, expires_hours=24)
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(hours=23, minutes=59)
        expected_max = after + timedelta(hours=24, minutes=1)
        assert expected_min <= expires_at <= expected_max

    def test_validate_signing_token_valid(self, crypto_service, sample_envelope_uuid):
        """A freshly generated token should validate successfully."""
        token, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        assert crypto_service.validate_signing_token(token, 42, sample_envelope_uuid) is True

    def test_validate_signing_token_wrong_recipient(self, crypto_service, sample_envelope_uuid):
        """Token should not validate with a different recipient_id."""
        token, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        assert crypto_service.validate_signing_token(token, 99, sample_envelope_uuid) is False

    def test_validate_signing_token_wrong_envelope(self, crypto_service, sample_envelope_uuid):
        """Token should not validate with a different envelope UUID."""
        token, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        wrong_envelope = str(uuid.uuid4())
        assert crypto_service.validate_signing_token(token, 42, wrong_envelope) is False

    def test_validate_signing_token_expired(self, crypto_service, sample_envelope_uuid):
        """An expired token should fail validation."""
        # Generate a token that expires in 1 hour, then time-travel past expiry
        token, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid, expires_hours=1)

        future_time = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch("services.smart_docs.esignature_crypto_service.datetime") as mock_dt:
            mock_dt.now.return_value = future_time
            mock_dt.fromtimestamp = datetime.fromtimestamp
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert crypto_service.validate_signing_token(token, 42, sample_envelope_uuid) is False

    def test_validate_signing_token_tampered_payload(self, crypto_service, sample_envelope_uuid):
        """A token with a tampered payload should fail HMAC verification."""
        token, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)

        # Decode, tamper with the payload bytes, re-encode
        token_raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload_b64, mac_b64 = token_raw.rsplit(b".", 1)
        # Decode the payload, flip a byte, re-encode
        payload_bytes = bytearray(base64.b64decode(payload_b64))
        payload_bytes[5] ^= 0xFF  # flip a byte in the payload
        tampered_payload_b64 = base64.b64encode(bytes(payload_bytes))
        tampered_raw = tampered_payload_b64 + b"." + mac_b64
        tampered_token = base64.urlsafe_b64encode(tampered_raw).decode("ascii")

        assert crypto_service.validate_signing_token(tampered_token, 99, sample_envelope_uuid) is False

    def test_validate_signing_token_garbage_input(self, crypto_service, sample_envelope_uuid):
        """Garbage token strings should return False, not raise."""
        assert crypto_service.validate_signing_token("not-a-valid-token!!!", 42, sample_envelope_uuid) is False
        assert crypto_service.validate_signing_token("", 42, sample_envelope_uuid) is False

    def test_token_uniqueness(self, crypto_service, sample_envelope_uuid):
        """Two tokens for the same recipient/envelope should differ (nonce)."""
        token1, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        token2, _ = crypto_service.generate_signing_token(42, sample_envelope_uuid)
        assert token1 != token2

    def test_token_payload_encoding_roundtrip(self, crypto_service, sample_envelope_uuid):
        """The payload embedded in the token should decode back to the original fields."""
        import struct
        recipient_id = 42
        token, _ = crypto_service.generate_signing_token(recipient_id, sample_envelope_uuid)

        # Manually decode to inspect the length-prefixed payload
        token_raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload_b64, _mac_b64 = token_raw.rsplit(b".", 1)
        payload_bytes = base64.b64decode(payload_b64)

        # Parse length-prefixed fields
        parts = []
        offset = 0
        while offset < len(payload_bytes):
            (length,) = struct.unpack(">I", payload_bytes[offset:offset + 4])
            offset += 4
            parts.append(payload_bytes[offset:offset + length].decode("utf-8"))
            offset += length

        assert len(parts) == 4
        assert parts[0] == str(recipient_id)
        assert parts[1] == sample_envelope_uuid
        # parts[2] is the expiry timestamp (should be a valid integer)
        int(parts[2])
        # parts[3] is the nonce (32-char hex)
        assert len(parts[3]) == 32
        int(parts[3], 16)


# =============================================================================
# 5. Certificate Generation
# =============================================================================

@pytest.mark.unit
class TestCertificateGeneration:
    """Tests for generate_completion_certificate."""

    def test_certificate_basic_structure(self, crypto_service, sample_envelope_uuid, sample_signer_info):
        """Certificate should have all required fields populated."""
        doc_hash = "a" * 64
        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=sample_envelope_uuid,
            title="Test Disclosure",
            signers=[sample_signer_info],
            document_hash=doc_hash,
        )

        assert isinstance(cert, SigningCertificate)
        assert cert.certificate_id.startswith("CERT-")
        assert len(cert.certificate_id) == 17  # "CERT-" + 12 hex chars
        assert cert.envelope_uuid == sample_envelope_uuid
        assert cert.signer_name == "Jane Doe"
        assert cert.signer_email == "jane.doe@example.com"
        assert cert.document_hash == doc_hash
        assert len(cert.signature_hash) == 64
        assert cert.ip_address == "192.168.1.100"
        assert "Mozilla" in cert.user_agent

    def test_certificate_verification_url(self, crypto_service, sample_envelope_uuid, sample_signer_info):
        """Verification URL should use the configured base URL and certificate ID."""
        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=sample_envelope_uuid,
            title="Test",
            signers=[sample_signer_info],
            document_hash="b" * 64,
        )
        assert cert.verification_url.startswith("https://test.example.com/verify/")
        assert cert.certificate_id in cert.verification_url

    def test_certificate_to_dict(self, crypto_service, sample_envelope_uuid, sample_signer_info):
        """to_dict should return a serializable dict with all fields."""
        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=sample_envelope_uuid,
            title="Test",
            signers=[sample_signer_info],
            document_hash="c" * 64,
        )
        d = cert.to_dict()
        assert isinstance(d, dict)
        assert d["certificate_id"] == cert.certificate_id
        assert d["envelope_uuid"] == sample_envelope_uuid
        assert d["document_hash"] == "c" * 64
        # Should be JSON-serializable
        json.dumps(d)

    def test_certificate_multiple_signers(self, crypto_service, sample_envelope_uuid):
        """With multiple signers, the last signer should be the primary on the certificate."""
        signer1 = {
            "name": "First Signer",
            "email": "first@example.com",
            "signed_at": "2026-03-10T10:00:00+00:00",
            "ip_address": "10.0.0.1",
            "user_agent": "Chrome/100",
        }
        signer2 = {
            "name": "Second Signer",
            "email": "second@example.com",
            "signed_at": "2026-03-10T11:00:00+00:00",
            "ip_address": "10.0.0.2",
            "user_agent": "Firefox/110",
        }

        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=sample_envelope_uuid,
            title="Multi-signer Doc",
            signers=[signer1, signer2],
            document_hash="d" * 64,
        )
        assert cert.signer_name == "Second Signer"
        assert cert.signer_email == "second@example.com"
        assert cert.ip_address == "10.0.0.2"

    def test_certificate_no_signers_raises(self, crypto_service, sample_envelope_uuid):
        """generate_completion_certificate with no signers should raise ValueError."""
        with pytest.raises(ValueError, match="At least one signer"):
            crypto_service.generate_completion_certificate(
                envelope_uuid=sample_envelope_uuid,
                title="Empty",
                signers=[],
                document_hash="e" * 64,
            )

    def test_certificate_composite_hash_changes_with_signers(self, crypto_service, sample_envelope_uuid):
        """Adding a signer should change the composite signature hash."""
        signer1 = {
            "name": "Solo",
            "email": "solo@example.com",
            "signed_at": "2026-03-10T12:00:00+00:00",
            "ip_address": "10.0.0.1",
            "user_agent": "TestAgent",
        }
        signer2 = {
            "name": "Extra",
            "email": "extra@example.com",
            "signed_at": "2026-03-10T13:00:00+00:00",
            "ip_address": "10.0.0.2",
            "user_agent": "TestAgent",
        }

        # Note: certificate_id includes a random UUID, so we cannot compare
        # signature hashes directly between calls. Instead, verify that
        # the signature hash is non-empty and 64 chars for both.
        cert1 = crypto_service.generate_completion_certificate(
            sample_envelope_uuid, "Doc", [signer1], "f" * 64,
        )
        cert2 = crypto_service.generate_completion_certificate(
            sample_envelope_uuid, "Doc", [signer1, signer2], "f" * 64,
        )
        assert len(cert1.signature_hash) == 64
        assert len(cert2.signature_hash) == 64
        # Different certificate_ids + different signer lists => different hashes
        assert cert1.signature_hash != cert2.signature_hash


# =============================================================================
# 6. Tamper Detection
# =============================================================================

@pytest.mark.unit
class TestTamperDetection:
    """Tests for verify_document_integrity."""

    def test_integrity_check_passes_for_unmodified(self, crypto_service, sample_document_content):
        """Unmodified document should pass integrity check."""
        original_hash = crypto_service.hash_document(sample_document_content)
        is_valid, current_hash = crypto_service.verify_document_integrity(original_hash, sample_document_content)
        assert is_valid is True
        assert current_hash == original_hash

    def test_integrity_check_fails_for_modified_document(self, crypto_service, sample_document_content):
        """Modified document should fail integrity check."""
        original_hash = crypto_service.hash_document(sample_document_content)
        tampered_content = sample_document_content + b" TAMPERED"
        is_valid, current_hash = crypto_service.verify_document_integrity(original_hash, tampered_content)
        assert is_valid is False
        assert current_hash != original_hash

    def test_integrity_check_detects_single_byte_change(self, crypto_service):
        """Even a single byte difference should be detected."""
        content = b"A" * 1000
        original_hash = crypto_service.hash_document(content)
        # Change one byte in the middle
        tampered = bytearray(content)
        tampered[500] = ord("B")
        is_valid, _ = crypto_service.verify_document_integrity(original_hash, bytes(tampered))
        assert is_valid is False


# =============================================================================
# 7. Hash Consistency Across Calls
# =============================================================================

@pytest.mark.unit
class TestHashConsistency:
    """Verify hashing is consistent across multiple service instances and calls."""

    def test_same_secret_same_signature_hash(self):
        """Two service instances with same secrets should produce identical signature hashes."""
        km1 = ESignatureKeyManager(
            signing_secret="shared-secret-for-consistency-test",
            token_secret="shared-token-secret-for-test-1234",
        )
        km2 = ESignatureKeyManager(
            signing_secret="shared-secret-for-consistency-test",
            token_secret="shared-token-secret-for-test-1234",
        )
        svc1 = ESignatureCryptoService(key_manager=km1)
        svc2 = ESignatureCryptoService(key_manager=km2)

        signed_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        kwargs = dict(
            document_hash="1" * 64,
            signer_email="test@test.com",
            signed_at=signed_at,
            ip_address="127.0.0.1",
        )
        assert svc1.generate_signature_hash(**kwargs) == svc2.generate_signature_hash(**kwargs)

    def test_document_hash_independent_of_service_secrets(self):
        """hash_document is pure SHA-256 and should not depend on service secrets."""
        km_a = ESignatureKeyManager(
            signing_secret="secret-A-that-is-at-least-32-chars!",
            token_secret=_TEST_TOKEN_SECRET,
        )
        km_b = ESignatureKeyManager(
            signing_secret="secret-B-that-is-at-least-32-chars!",
            token_secret=_TEST_TOKEN_SECRET,
        )
        svc_a = ESignatureCryptoService(key_manager=km_a)
        svc_b = ESignatureCryptoService(key_manager=km_b)

        content = b"same content"
        assert svc_a.hash_document(content) == svc_b.hash_document(content)


# =============================================================================
# 9. Key Derivation for Different Tenants / Service Instances
# =============================================================================

@pytest.mark.unit
class TestKeyIsolation:
    """Different signing secrets must produce different signature hashes."""

    def test_different_signing_secrets_different_hashes(self):
        """Two services with different signing secrets should produce different signature hashes."""
        km_a = ESignatureKeyManager(
            signing_secret="tenant-A-secret-32-bytes-long!!",
            token_secret=_TEST_TOKEN_SECRET,
        )
        km_b = ESignatureKeyManager(
            signing_secret="tenant-B-secret-32-bytes-long!!",
            token_secret=_TEST_TOKEN_SECRET,
        )
        svc_a = ESignatureCryptoService(key_manager=km_a)
        svc_b = ESignatureCryptoService(key_manager=km_b)

        signed_at = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        kwargs = dict(
            document_hash="2" * 64,
            signer_email="user@tenant.com",
            signed_at=signed_at,
            ip_address="10.0.0.1",
        )
        hash_a = svc_a.generate_signature_hash(**kwargs)
        hash_b = svc_b.generate_signature_hash(**kwargs)
        assert hash_a != hash_b

    def test_different_token_secrets_incompatible_tokens(self):
        """A token generated with secret A should not validate with secret B."""
        envelope = str(uuid.uuid4())
        km_a = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret="token-secret-A-32-bytes-long!!!",
        )
        km_b = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret="token-secret-B-32-bytes-long!!!",
        )
        svc_a = ESignatureCryptoService(key_manager=km_a)
        svc_b = ESignatureCryptoService(key_manager=km_b)

        token, _ = svc_a.generate_signing_token(1, envelope)
        # Should fail because svc_b has a different token secret
        assert svc_b.validate_signing_token(token, 1, envelope) is False

    def test_missing_env_vars_raises_runtime_error(self):
        """When ESIGN_SIGNING_SECRET is unset, ESignatureCryptoService must refuse to start."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the keys entirely
            for key in ("ESIGN_SIGNING_SECRET", "ESIGN_TOKEN_SECRET", "ESIGN_VERIFY_BASE_URL"):
                os.environ.pop(key, None)
            with pytest.raises(RuntimeError, match="ESIGN_SIGNING_SECRET"):
                ESignatureCryptoService()


# =============================================================================
# 10. Edge Cases
# =============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Edge case handling: empty, very large, unicode, and boundary inputs."""

    def test_hash_empty_document(self, crypto_service):
        """Empty document hashing should succeed (tested above but grouped here)."""
        result = crypto_service.hash_document(b"")
        assert len(result) == 64

    def test_signature_with_unicode_email(self, crypto_service):
        """Unicode characters in email should be handled."""
        signed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # IDN email
        result = crypto_service.generate_signature_hash(
            "a" * 64, "user@example.com", signed_at, "::1",
        )
        assert len(result) == 64

    def test_signature_with_ipv6_address(self, crypto_service):
        """IPv6 addresses should be handled in signature generation."""
        signed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = crypto_service.generate_signature_hash(
            "a" * 64, "user@test.com", signed_at, "2001:0db8:85a3::8a2e:0370:7334",
        )
        assert len(result) == 64

    def test_certificate_with_missing_optional_fields(self, crypto_service, sample_envelope_uuid):
        """Signer dicts with missing optional fields should use defaults."""
        minimal_signer = {"email": "min@test.com"}
        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=sample_envelope_uuid,
            title="Minimal",
            signers=[minimal_signer],
            document_hash="a" * 64,
        )
        assert cert.signer_name == "Unknown"
        assert cert.ip_address == "unknown"
        assert cert.user_agent == "unknown"

    def test_generate_envelope_uuid_format(self, crypto_service):
        """generate_envelope_uuid should return a valid UUID4 string."""
        result = crypto_service.generate_envelope_uuid()
        parsed = uuid.UUID(result)
        assert parsed.version == 4
        assert str(parsed) == result


# =============================================================================
# 11. Access Codes and SMS Verification
# =============================================================================

@pytest.mark.unit
class TestAccessCodes:
    """Tests for access code generation, hashing, and verification."""

    def test_generate_access_code_format(self, crypto_service):
        """Access code should be a 6-digit zero-padded string."""
        code = crypto_service.generate_access_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_sms_verification_code_format(self, crypto_service):
        """SMS verification code should be a 6-digit zero-padded string."""
        code = crypto_service.generate_sms_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_access_code_hash_and_verify(self, crypto_service):
        """hash_access_code + verify_access_code should round-trip correctly."""
        code = "042817"
        hashed = crypto_service.hash_access_code(code)
        assert isinstance(hashed, str)
        assert len(hashed) == 64
        assert crypto_service.verify_access_code(code, hashed) is True

    def test_access_code_verify_wrong_code(self, crypto_service):
        """verify_access_code should return False for wrong code."""
        code = "123456"
        hashed = crypto_service.hash_access_code(code)
        assert crypto_service.verify_access_code("654321", hashed) is False

    def test_access_code_hash_deterministic(self, crypto_service):
        """Same code should always produce the same hash."""
        code = "999999"
        hash1 = crypto_service.hash_access_code(code)
        hash2 = crypto_service.hash_access_code(code)
        assert hash1 == hash2

    def test_different_codes_different_hashes(self, crypto_service):
        """Different codes should produce different hashes."""
        hash1 = crypto_service.hash_access_code("000000")
        hash2 = crypto_service.hash_access_code("000001")
        assert hash1 != hash2


# =============================================================================
# 12. Audit Trail / Signature Chain Integrity
# =============================================================================

@pytest.mark.unit
class TestAuditTrailIntegrity:
    """Tests for generate_audit_hash and audit trail consistency."""

    def test_audit_hash_deterministic(self, crypto_service):
        """Same events should produce the same audit hash."""
        events = [
            {"action": "envelope_created", "timestamp": "2026-03-10T10:00:00Z", "actor": "system"},
            {"action": "recipient_signed", "timestamp": "2026-03-10T11:00:00Z", "actor": "signer@test.com"},
        ]
        hash1 = crypto_service.generate_audit_hash(events)
        hash2 = crypto_service.generate_audit_hash(events)
        assert hash1 == hash2

    def test_audit_hash_changes_on_event_modification(self, crypto_service):
        """Modifying any event should change the audit hash."""
        events = [
            {"action": "envelope_created", "timestamp": "2026-03-10T10:00:00Z", "actor": "system"},
        ]
        hash1 = crypto_service.generate_audit_hash(events)

        tampered_events = [
            {"action": "envelope_created", "timestamp": "2026-03-10T10:00:01Z", "actor": "system"},
        ]
        hash2 = crypto_service.generate_audit_hash(tampered_events)
        assert hash1 != hash2

    def test_audit_hash_changes_on_event_removal(self, crypto_service):
        """Removing an event should change the audit hash."""
        events = [
            {"action": "created", "timestamp": "2026-03-10T10:00:00Z", "actor": "sys"},
            {"action": "signed", "timestamp": "2026-03-10T11:00:00Z", "actor": "user"},
        ]
        full_hash = crypto_service.generate_audit_hash(events)
        partial_hash = crypto_service.generate_audit_hash(events[:1])
        assert full_hash != partial_hash

    def test_audit_hash_dict_key_order_independence(self, crypto_service):
        """Dict key order should not affect the audit hash (sorted keys)."""
        events_a = [{"actor": "sys", "action": "created", "timestamp": "2026-03-10T10:00:00Z"}]
        events_b = [{"timestamp": "2026-03-10T10:00:00Z", "action": "created", "actor": "sys"}]
        assert crypto_service.generate_audit_hash(events_a) == crypto_service.generate_audit_hash(events_b)

    def test_audit_hash_empty_events(self, crypto_service):
        """Empty event list should produce a valid hash."""
        result = crypto_service.generate_audit_hash([])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_signature_chain_integrity(self, crypto_service):
        """Simulate a signature chain: each event hash depends on the previous."""
        events = []
        hashes = []

        event1 = {"action": "envelope_created", "timestamp": "2026-03-10T10:00:00Z", "actor": "system"}
        events.append(event1)
        hashes.append(crypto_service.generate_audit_hash(events))

        event2 = {"action": "signer_1_signed", "timestamp": "2026-03-10T11:00:00Z", "actor": "signer1@test.com", "prev_hash": hashes[-1]}
        events.append(event2)
        hashes.append(crypto_service.generate_audit_hash(events))

        event3 = {"action": "signer_2_signed", "timestamp": "2026-03-10T12:00:00Z", "actor": "signer2@test.com", "prev_hash": hashes[-1]}
        events.append(event3)
        hashes.append(crypto_service.generate_audit_hash(events))

        # All hashes should be unique
        assert len(set(hashes)) == 3

        # Recomputing the final hash from the full event list should match
        assert crypto_service.generate_audit_hash(events) == hashes[-1]

        # Tampering with event2 should change the final hash
        events_tampered = events.copy()
        events_tampered[1] = {**events_tampered[1], "actor": "attacker@evil.com"}
        assert crypto_service.generate_audit_hash(events_tampered) != hashes[-1]


# =============================================================================
# Signing Payload Creation
# =============================================================================

@pytest.mark.unit
class TestSigningPayload:
    """Tests for create_signing_payload."""

    def test_signing_payload_structure(self, crypto_service, sample_signer_info):
        """Payload should contain payload dict, payload_hash, and created_at."""
        doc_hash = "a" * 64
        fields = [
            {"field_id": "sig_1", "field_type": "signature", "value": "base64data"},
            {"field_id": "date_1", "field_type": "date", "value": "2026-03-10"},
        ]
        result = crypto_service.create_signing_payload(doc_hash, fields, sample_signer_info)

        assert "payload" in result
        assert "payload_hash" in result
        assert "created_at" in result

        payload = result["payload"]
        assert payload["document_hash"] == doc_hash
        assert payload["version"] == "1.0"
        assert "signer" in payload
        assert payload["signer"]["email"] == "jane.doe@example.com"

    def test_signing_payload_hash_is_valid_hex(self, crypto_service, sample_signer_info):
        """payload_hash should be a 64-char hex string."""
        result = crypto_service.create_signing_payload("b" * 64, [], sample_signer_info)
        assert len(result["payload_hash"]) == 64
        int(result["payload_hash"], 16)

    def test_signing_payload_fields_sorted(self, crypto_service, sample_signer_info):
        """Fields in the payload should be sorted by field_id."""
        fields = [
            {"field_id": "z_field", "field_type": "text", "value": "Z"},
            {"field_id": "a_field", "field_type": "text", "value": "A"},
            {"field_id": "m_field", "field_type": "text", "value": "M"},
        ]
        result = crypto_service.create_signing_payload("c" * 64, fields, sample_signer_info)
        payload_fields = result["payload"]["fields"]
        field_ids = [f["field_id"] for f in payload_fields]
        assert field_ids == ["a_field", "m_field", "z_field"]

    def test_signing_payload_email_normalized(self, crypto_service):
        """Signer email in payload should be lowercased and stripped."""
        signer = {"email": "  USER@EXAMPLE.COM  ", "name": "Test", "ip_address": "1.2.3.4", "user_agent": "Test"}
        result = crypto_service.create_signing_payload("d" * 64, [], signer)
        assert result["payload"]["signer"]["email"] == "user@example.com"


# =============================================================================
# Singleton
# =============================================================================

@pytest.mark.unit
class TestSingleton:
    """Test the module-level get_esignature_crypto_service singleton."""

    def test_singleton_returns_same_instance(self):
        """get_esignature_crypto_service should return the same instance on repeated calls."""
        import services.smart_docs.esignature_crypto_service as mod
        mod._service = None
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            svc1 = get_esignature_crypto_service()
            svc2 = get_esignature_crypto_service()
        assert svc1 is svc2
        # Clean up
        mod._service = None
