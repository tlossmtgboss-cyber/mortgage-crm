"""
Tests for SOC 2 Compliance Module

Run with: pytest tests/test_audit_service.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from soc2_compliance.constants import AuditAction, SeverityLevel, PII_FIELDS
from soc2_compliance.services.encryption_service import EncryptionService
from soc2_compliance.config import SOC2Config


# ============================================================================
# Encryption Service Tests
# ============================================================================

class TestEncryptionService:
    """Test field-level encryption."""

    def setup_method(self):
        """Create encryption service with a test key."""
        from cryptography.fernet import Fernet
        self.test_key = Fernet.generate_key().decode()
        self.config = SOC2Config(field_encryption_key=self.test_key)
        self.enc = EncryptionService(config=self.config)

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted value should decrypt back to original."""
        original = "123-45-6789"
        encrypted = self.enc.encrypt(original)
        assert encrypted != original
        assert self.enc.decrypt(encrypted) == original

    def test_encrypt_empty_string(self):
        """Empty string should pass through."""
        assert self.enc.encrypt("") == ""
        assert self.enc.decrypt("") == ""

    def test_different_encryptions_differ(self):
        """Same plaintext should produce different ciphertext (Fernet uses random IV)."""
        val = "test-value"
        enc1 = self.enc.encrypt(val)
        enc2 = self.enc.encrypt(val)
        assert enc1 != enc2  # Different IVs

    def test_mask_value(self):
        """Masking should show only last N chars."""
        assert self.enc.mask_value("123-45-6789", 4) == "***6789"
        assert self.enc.mask_value("abc", 4) == "****"
        assert self.enc.mask_value("", 4) == "****"

    def test_hash_value_deterministic(self):
        """Same input + salt should produce same hash."""
        h1 = self.enc.hash_value("123-45-6789", salt="test-salt")
        h2 = self.enc.hash_value("123-45-6789", salt="test-salt")
        assert h1 == h2

    def test_hash_value_different_salts(self):
        """Different salts should produce different hashes."""
        h1 = self.enc.hash_value("123-45-6789", salt="salt-a")
        h2 = self.enc.hash_value("123-45-6789", salt="salt-b")
        assert h1 != h2

    def test_is_encrypted_detection(self):
        """Should detect Fernet-encrypted values."""
        encrypted = self.enc.encrypt("test")
        assert self.enc.is_encrypted(encrypted) is True
        assert self.enc.is_encrypted("plain text") is False
        assert self.enc.is_encrypted("") is False

    def test_no_key_raises_error(self):
        """Missing encryption key should raise on encrypt/decrypt."""
        enc = EncryptionService(config=SOC2Config(field_encryption_key=""))
        with pytest.raises(ValueError, match="not configured"):
            enc.encrypt("test")

    def test_generate_key(self):
        """Should generate a valid Fernet key."""
        key = EncryptionService.generate_key()
        assert len(key) == 44  # Base64-encoded 32 bytes


# ============================================================================
# Configuration Tests
# ============================================================================

class TestSOC2Config:
    """Test configuration loading."""

    def test_default_values(self):
        config = SOC2Config()
        assert config.session_timeout_minutes == 30
        assert config.max_login_attempts == 5
        assert config.password_min_length == 12
        assert config.audit_retention_days == 730

    @patch.dict("os.environ", {
        "SOC2_SESSION_TIMEOUT_MINUTES": "15",
        "SOC2_MAX_LOGIN_ATTEMPTS": "3",
        "SOC2_REQUIRE_MFA": "false",
    })
    def test_from_env(self):
        config = SOC2Config.from_env()
        assert config.session_timeout_minutes == 15
        assert config.max_login_attempts == 3
        assert config.require_mfa is False


# ============================================================================
# Constants Tests
# ============================================================================

class TestConstants:
    """Test constants and PII field detection."""

    def test_pii_fields_include_mortgage_data(self):
        """PII fields should include mortgage-specific sensitive data."""
        assert "ssn" in PII_FIELDS
        assert "bank_account" in PII_FIELDS
        assert "routing_number" in PII_FIELDS
        assert "credit_score" in PII_FIELDS
        assert "income" in PII_FIELDS

    def test_audit_actions_comprehensive(self):
        """Should have all essential audit actions."""
        assert AuditAction.CREATE
        assert AuditAction.READ
        assert AuditAction.UPDATE
        assert AuditAction.DELETE
        assert AuditAction.LOGIN
        assert AuditAction.LOGIN_FAILED
        assert AuditAction.PERMISSION_CHANGE


# ============================================================================
# Audit Service — PII Sanitization Tests
# ============================================================================

class TestAuditServiceSanitization:
    """Test PII detection and sanitization logic."""

    def setup_method(self):
        from soc2_compliance.services.audit_service import AuditService
        self.service = AuditService.__new__(AuditService)

    def test_pii_detection_in_fields(self):
        """Should detect PII in fields_accessed list."""
        assert self.service._check_pii_involvement(
            fields_accessed=["name", "ssn", "address"],
            old_values=None,
            new_values=None,
        ) is True

    def test_pii_detection_in_values(self):
        """Should detect PII in old/new values."""
        assert self.service._check_pii_involvement(
            fields_accessed=None,
            old_values={"income": 75000},
            new_values=None,
        ) is True

    def test_no_pii_detection(self):
        """Should not flag non-PII fields."""
        assert self.service._check_pii_involvement(
            fields_accessed=["name", "status", "loan_type"],
            old_values=None,
            new_values=None,
        ) is False

    def test_sanitize_values_redacts_pii(self):
        """Should fully redact PII values."""
        result = self.service._sanitize_values({
            "ssn": "123-45-6789",
            "name": "John Doe",
            "income": "75000",
        })
        assert result["ssn"] == "***REDACTED***"
        assert result["name"] == "John Doe"  # Not PII
        assert result["income"] == "***REDACTED***"

    def test_sanitize_short_values(self):
        """Short PII values should be fully redacted."""
        result = self.service._sanitize_values({"ssn": "123"})
        assert result["ssn"] == "***REDACTED***"
