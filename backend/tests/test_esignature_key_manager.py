"""
Test E-Signature Key Manager

Tests for centralized key management:
- Missing env vars raises RuntimeError
- Key derivation produces different keys for different purposes
- HMAC with length-prefixed encoding prevents field-boundary attacks
- Key rotation: verify with both current and previous key
- Health check passes with valid keys, fails without
- Minimum secret length enforcement
"""

import hashlib
import hmac as hmac_mod
import os
import struct
from unittest.mock import patch

import pytest

from services.smart_docs.esignature_key_manager import (
    ESignatureKeyManager,
    get_esignature_key_manager,
    reset_key_manager,
    length_prefix_encode,
    _hkdf_derive,
    _INFO_SIGNING,
    _INFO_TOKEN,
    _INFO_AUDIT,
)


# =============================================================================
# Fixtures
# =============================================================================

_TEST_SIGNING_SECRET = "test-signing-secret-at-least-32-chars-long!!"
_TEST_TOKEN_SECRET = "test-token-secret-at-least-32-characters!!"


@pytest.fixture
def key_manager():
    """Create a key manager with deterministic test secrets."""
    return ESignatureKeyManager(
        signing_secret=_TEST_SIGNING_SECRET,
        token_secret=_TEST_TOKEN_SECRET,
    )


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module singleton before each test."""
    reset_key_manager()
    yield
    reset_key_manager()


# =============================================================================
# Missing env vars raises RuntimeError
# =============================================================================

class TestMissingEnvVars:
    """Verify that the key manager refuses to start without required env vars."""

    def test_missing_signing_secret_raises(self):
        """RuntimeError when ESIGN_SIGNING_SECRET is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure both vars are absent
            os.environ.pop("ESIGN_SIGNING_SECRET", None)
            os.environ.pop("ESIGN_TOKEN_SECRET", None)
            with pytest.raises(RuntimeError, match="ESIGN_SIGNING_SECRET"):
                ESignatureKeyManager()

    def test_missing_token_secret_raises(self):
        """RuntimeError when ESIGN_TOKEN_SECRET is not set."""
        with patch.dict(os.environ, {"ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET}, clear=True):
            os.environ.pop("ESIGN_TOKEN_SECRET", None)
            with pytest.raises(RuntimeError, match="ESIGN_TOKEN_SECRET"):
                ESignatureKeyManager()

    def test_empty_signing_secret_raises(self):
        """Empty string is treated as missing."""
        with pytest.raises(RuntimeError, match="ESIGN_SIGNING_SECRET"):
            ESignatureKeyManager(signing_secret="", token_secret=_TEST_TOKEN_SECRET)

    def test_empty_token_secret_raises(self):
        """Empty string is treated as missing."""
        with pytest.raises(RuntimeError, match="ESIGN_TOKEN_SECRET"):
            ESignatureKeyManager(signing_secret=_TEST_SIGNING_SECRET, token_secret="")

    def test_short_signing_secret_raises(self):
        """Secrets shorter than 32 chars are rejected."""
        with pytest.raises(RuntimeError, match="too short"):
            ESignatureKeyManager(
                signing_secret="short",
                token_secret=_TEST_TOKEN_SECRET,
            )

    def test_short_token_secret_raises(self):
        """Secrets shorter than 32 chars are rejected."""
        with pytest.raises(RuntimeError, match="too short"):
            ESignatureKeyManager(
                signing_secret=_TEST_SIGNING_SECRET,
                token_secret="short",
            )

    def test_singleton_raises_without_env(self):
        """The module-level singleton factory also raises."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ESIGN_SIGNING_SECRET", None)
            os.environ.pop("ESIGN_TOKEN_SECRET", None)
            with pytest.raises(RuntimeError, match="ESIGN_SIGNING_SECRET"):
                get_esignature_key_manager()


# =============================================================================
# Key derivation produces different keys
# =============================================================================

class TestKeyDerivation:
    """Verify that HKDF produces distinct keys for each purpose."""

    def test_signing_and_token_keys_differ(self, key_manager):
        """Signing key must differ from token key."""
        assert key_manager.get_signing_key() != key_manager.get_token_key()

    def test_signing_and_audit_keys_differ(self, key_manager):
        """Signing key must differ from audit key."""
        assert key_manager.get_signing_key() != key_manager.get_audit_key()

    def test_token_and_audit_keys_differ(self, key_manager):
        """Token key must differ from audit key."""
        assert key_manager.get_token_key() != key_manager.get_audit_key()

    def test_keys_are_32_bytes(self, key_manager):
        """All derived keys should be 32 bytes (256-bit)."""
        assert len(key_manager.get_signing_key()) == 32
        assert len(key_manager.get_token_key()) == 32
        assert len(key_manager.get_audit_key()) == 32

    def test_same_secret_produces_same_keys(self):
        """Determinism: same input secrets always yield the same keys."""
        km1 = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret=_TEST_TOKEN_SECRET,
        )
        km2 = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret=_TEST_TOKEN_SECRET,
        )
        assert km1.get_signing_key() == km2.get_signing_key()
        assert km1.get_token_key() == km2.get_token_key()
        assert km1.get_audit_key() == km2.get_audit_key()

    def test_different_secrets_produce_different_keys(self):
        """Different master secrets produce different derived keys."""
        km1 = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret=_TEST_TOKEN_SECRET,
        )
        km2 = ESignatureKeyManager(
            signing_secret="another-signing-secret-that-is-32-chars!",
            token_secret=_TEST_TOKEN_SECRET,
        )
        assert km1.get_signing_key() != km2.get_signing_key()
        assert km1.get_audit_key() != km2.get_audit_key()
        # Token key should be the same since token_secret is the same
        assert km1.get_token_key() == km2.get_token_key()

    def test_hkdf_info_produces_different_output(self):
        """Different info strings yield different keys from same master."""
        master = b"same-master-secret-for-all-derivations"
        key_a = _hkdf_derive(master, _INFO_SIGNING)
        key_b = _hkdf_derive(master, _INFO_TOKEN)
        key_c = _hkdf_derive(master, _INFO_AUDIT)
        assert key_a != key_b
        assert key_b != key_c
        assert key_a != key_c


# =============================================================================
# Length-prefixed encoding
# =============================================================================

class TestLengthPrefixedEncoding:
    """Verify that length-prefixed encoding prevents field-boundary attacks."""

    def test_basic_encoding(self):
        """Fields are encoded with 4-byte big-endian length prefixes."""
        encoded = length_prefix_encode("hello", "world")
        # "hello" = 5 bytes, "world" = 5 bytes
        assert encoded == (
            struct.pack(">I", 5) + b"hello" +
            struct.pack(">I", 5) + b"world"
        )

    def test_empty_fields(self):
        """Empty strings produce zero-length prefixes."""
        encoded = length_prefix_encode("", "a")
        assert encoded == (
            struct.pack(">I", 0) + b"" +
            struct.pack(">I", 1) + b"a"
        )

    def test_pipe_in_field_is_safe(self):
        """A pipe character inside a field does not cause boundary confusion."""
        # This is the key security property: with pipe-separated encoding,
        # these two produce the same string "a|b|c".
        encoding_a = length_prefix_encode("a|b", "c")
        encoding_b = length_prefix_encode("a", "b|c")
        assert encoding_a != encoding_b

    def test_field_boundary_attack_prevented(self):
        """Attacker cannot craft fields that produce same encoding as different fields."""
        # More elaborate attack: attacker tries to shift field boundaries
        attack_1 = length_prefix_encode("admin", "user@evil.com", "2025-01-01")
        attack_2 = length_prefix_encode("admin", "user@evil.com|2025-01-01")
        assert attack_1 != attack_2

    def test_unicode_encoding(self):
        """Unicode characters are correctly length-prefixed by byte length."""
        encoded = length_prefix_encode("cafe\u0301")  # e + combining accent
        utf8_bytes = "cafe\u0301".encode("utf-8")
        assert encoded == struct.pack(">I", len(utf8_bytes)) + utf8_bytes

    def test_hmac_with_length_prefix_is_secure(self, key_manager):
        """HMACs over length-prefixed messages are distinct for boundary-shifted inputs."""
        key = key_manager.get_signing_key()

        msg_a = length_prefix_encode("a|b", "c")
        msg_b = length_prefix_encode("a", "b|c")

        mac_a = hmac_mod.new(key, msg_a, hashlib.sha256).hexdigest()
        mac_b = hmac_mod.new(key, msg_b, hashlib.sha256).hexdigest()
        assert mac_a != mac_b


# =============================================================================
# Key rotation
# =============================================================================

class TestKeyRotation:
    """Verify that key rotation allows verifying both old and new signatures."""

    def test_rotate_keys_returns_new_manager(self, key_manager):
        """rotate_keys() returns a new manager with different signing key."""
        new_secret = "brand-new-signing-secret-at-least-32-chars!"
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            rotated = key_manager.rotate_keys(new_secret)
        assert rotated.get_signing_key() != key_manager.get_signing_key()

    def test_rotated_manager_has_previous_key(self, key_manager):
        """The rotated manager keeps the old key for verification."""
        new_secret = "brand-new-signing-secret-at-least-32-chars!"
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            rotated = key_manager.rotate_keys(new_secret)
        assert rotated.get_previous_signing_key() is not None

    def test_verify_old_signature_after_rotation(self, key_manager):
        """Signatures made with the old key verify after rotation."""
        # Sign with original key
        message = b"document-hash-content"
        old_mac = hmac_mod.new(
            key_manager.get_signing_key(), message, hashlib.sha256,
        ).hexdigest()

        # Rotate keys
        new_secret = "brand-new-signing-secret-at-least-32-chars!"
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            rotated = key_manager.rotate_keys(new_secret)

        # Old signature should still verify via rotation fallback
        assert rotated.verify_with_rotation(message, old_mac) is True

    def test_verify_new_signature_after_rotation(self, key_manager):
        """Signatures made with the new key also verify."""
        new_secret = "brand-new-signing-secret-at-least-32-chars!"
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            rotated = key_manager.rotate_keys(new_secret)

        message = b"new-document-content"
        new_mac = hmac_mod.new(
            rotated.get_signing_key(), message, hashlib.sha256,
        ).hexdigest()
        assert rotated.verify_with_rotation(message, new_mac) is True

    def test_invalid_signature_fails_even_with_rotation(self, key_manager):
        """A completely bogus MAC fails even with rotation enabled."""
        new_secret = "brand-new-signing-secret-at-least-32-chars!"
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            rotated = key_manager.rotate_keys(new_secret)

        assert rotated.verify_with_rotation(b"data", "0" * 64) is False

    def test_rotate_rejects_short_secret(self, key_manager):
        """rotate_keys() rejects secrets that are too short."""
        with pytest.raises(ValueError, match="too short"):
            key_manager.rotate_keys("short")

    def test_no_previous_key_without_rotation(self, key_manager):
        """Without rotation, there is no previous signing key."""
        assert key_manager.get_previous_signing_key() is None

    def test_verify_without_rotation_rejects_wrong_key(self, key_manager):
        """Without a previous key, only the current key verifies."""
        message = b"some-data"
        wrong_mac = hmac_mod.new(
            b"totally-wrong-key-000000000000000", message, hashlib.sha256,
        ).hexdigest()
        assert key_manager.verify_with_rotation(message, wrong_mac) is False


# =============================================================================
# Health check
# =============================================================================

class TestHealthCheck:
    """Verify the health check mechanism."""

    def test_health_check_passes(self, key_manager):
        """Health check returns healthy=True for a properly initialised manager."""
        result = key_manager.health_check()
        assert result["healthy"] is True
        assert "initialized_at" in result

    def test_health_check_reports_rotation_key(self):
        """Health check reports whether a rotation key is present."""
        km = ESignatureKeyManager(
            signing_secret=_TEST_SIGNING_SECRET,
            token_secret=_TEST_TOKEN_SECRET,
            _previous_signing_secret="old-signing-secret-at-least-32-characters!",
        )
        result = km.health_check()
        assert result["healthy"] is True
        assert result["has_rotation_key"] is True

    def test_health_check_no_rotation_key(self, key_manager):
        """Without rotation, has_rotation_key is False."""
        result = key_manager.health_check()
        assert result["has_rotation_key"] is False

    def test_health_check_detects_corruption(self, key_manager):
        """If the signing key is corrupted in memory, health check fails."""
        # Corrupt the test signature (simulating memory corruption)
        key_manager._test_signature = "0" * 64
        result = key_manager.health_check()
        assert result["healthy"] is False
        assert "corrupted" in result.get("error", "")


# =============================================================================
# Singleton lifecycle
# =============================================================================

class TestSingleton:
    """Test the module-level singleton factory."""

    def test_singleton_returns_same_instance(self):
        """Repeated calls return the same instance."""
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            km1 = get_esignature_key_manager()
            km2 = get_esignature_key_manager()
            assert km1 is km2

    def test_reset_clears_singleton(self):
        """reset_key_manager() clears the cached instance."""
        with patch.dict(os.environ, {
            "ESIGN_SIGNING_SECRET": _TEST_SIGNING_SECRET,
            "ESIGN_TOKEN_SECRET": _TEST_TOKEN_SECRET,
        }):
            km1 = get_esignature_key_manager()
            reset_key_manager()
            km2 = get_esignature_key_manager()
            assert km1 is not km2
            # But keys should be identical (same env vars)
            assert km1.get_signing_key() == km2.get_signing_key()
