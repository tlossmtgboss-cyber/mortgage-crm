"""
Tests for PII Encryption Service (Smart Docs V2)

Covers:
  - Encrypt / decrypt round-trip
  - None-safe field handling
  - SSN masking
  - Account number masking
  - Phone number masking
  - PII detection in free text
  - PII redaction in free text
  - Dict-level encrypt / decrypt
  - Log filter catches SSN patterns
  - Missing encryption key raises RuntimeError
  - Encrypted data is not readable without the correct key
"""

import logging
import os
import re

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_crypto():
    """Skip test module if the ``cryptography`` library is not installed."""
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return True
    except ImportError:
        return False


HAS_CRYPTO = _ensure_crypto()


def _generate_key() -> str:
    """Generate a fresh Fernet key for test isolation."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module-level singleton between tests."""
    from services.smart_docs.pii_encryption_service import reset_pii_encryption_service
    reset_pii_encryption_service()
    yield
    reset_pii_encryption_service()


@pytest.fixture()
def encryption_key(monkeypatch):
    """Set a valid PII_ENCRYPTION_KEY for the duration of a test."""
    if not HAS_CRYPTO:
        pytest.skip("cryptography library not installed")
    key = _generate_key()
    monkeypatch.setenv("PII_ENCRYPTION_KEY", key)
    return key


@pytest.fixture()
def svc(encryption_key):
    """Return a fresh PIIEncryptionService instance with a valid key."""
    from services.smart_docs.pii_encryption_service import PIIEncryptionService
    return PIIEncryptionService()


# =========================================================================
# Encrypt / Decrypt Round-Trip
# =========================================================================

@pytest.mark.unit
class TestEncryptDecrypt:
    """Core encryption and decryption."""

    def test_roundtrip_ascii(self, svc):
        plaintext = "123-45-6789"
        encrypted = svc.encrypt(plaintext)
        assert encrypted != plaintext, "Encrypted value must differ from plaintext"
        assert svc.decrypt(encrypted) == plaintext

    def test_roundtrip_unicode(self, svc):
        plaintext = "Borrower: Jose Garcia, SSN 123-45-6789"
        encrypted = svc.encrypt(plaintext)
        assert svc.decrypt(encrypted) == plaintext

    def test_roundtrip_empty_string(self, svc):
        encrypted = svc.encrypt("")
        assert svc.decrypt(encrypted) == ""

    def test_roundtrip_long_text(self, svc):
        """OCR text can be very long."""
        plaintext = "A" * 50_000
        encrypted = svc.encrypt(plaintext)
        assert svc.decrypt(encrypted) == plaintext

    def test_encrypted_is_base64(self, svc):
        encrypted = svc.encrypt("test")
        # Fernet tokens are URL-safe base64
        assert re.match(r"^[A-Za-z0-9_\-=]+$", encrypted)


# =========================================================================
# None-Safe Field Handling
# =========================================================================

@pytest.mark.unit
class TestFieldNullSafety:

    def test_encrypt_field_none(self, svc):
        assert svc.encrypt_field(None) is None

    def test_decrypt_field_none(self, svc):
        assert svc.decrypt_field(None) is None

    def test_encrypt_field_with_value(self, svc):
        encrypted = svc.encrypt_field("sensitive")
        assert encrypted is not None
        assert encrypted != "sensitive"
        assert svc.decrypt_field(encrypted) == "sensitive"


# =========================================================================
# SSN Masking
# =========================================================================

@pytest.mark.unit
class TestSSNMasking:

    def test_mask_ssn_with_hyphens(self, svc):
        assert svc.mask_ssn("123-45-6789") == "***-**-6789"

    def test_mask_ssn_digits_only(self, svc):
        assert svc.mask_ssn("123456789") == "***-**-6789"

    def test_mask_ssn_short(self, svc):
        assert svc.mask_ssn("12") == "***-**-****"

    def test_mask_ssn_with_spaces(self, svc):
        assert svc.mask_ssn("123 45 6789") == "***-**-6789"


# =========================================================================
# Account Number Masking
# =========================================================================

@pytest.mark.unit
class TestAccountMasking:

    def test_mask_account_8_digits(self, svc):
        result = svc.mask_account("12345678")
        assert result == "****5678"

    def test_mask_account_12_digits(self, svc):
        result = svc.mask_account("123456789012")
        assert result == "********9012"

    def test_mask_account_short(self, svc):
        assert svc.mask_account("12") == "****"


# =========================================================================
# Phone Number Masking
# =========================================================================

@pytest.mark.unit
class TestPhoneMasking:

    def test_mask_phone_formatted(self, svc):
        assert svc.mask_phone("(555) 123-4567") == "(***) ***-4567"

    def test_mask_phone_digits_only(self, svc):
        assert svc.mask_phone("5551234567") == "(***) ***-4567"

    def test_mask_phone_short(self, svc):
        assert svc.mask_phone("12") == "(***) ***-****"


# =========================================================================
# PII Detection
# =========================================================================

@pytest.mark.unit
class TestPIIDetection:

    def test_detect_ssn(self, svc):
        detections = svc.detect_pii("My SSN is 123-45-6789 thanks")
        ssn_dets = [d for d in detections if d.pii_type.value == "SSN"]
        assert len(ssn_dets) >= 1
        assert "6789" in ssn_dets[0].masked

    def test_detect_email(self, svc):
        detections = svc.detect_pii("Email: borrower@example.com")
        email_dets = [d for d in detections if d.pii_type.value == "EMAIL"]
        assert len(email_dets) == 1

    def test_detect_phone(self, svc):
        detections = svc.detect_pii("Call me at (555) 867-5309")
        phone_dets = [d for d in detections if d.pii_type.value == "PHONE"]
        assert len(phone_dets) == 1

    def test_detect_account_number(self, svc):
        detections = svc.detect_pii("Account# 1234567890123")
        acct_dets = [d for d in detections if d.pii_type.value == "ACCOUNT_NUMBER"]
        assert len(acct_dets) == 1

    def test_detect_multiple_types(self, svc):
        text = (
            "SSN: 123-45-6789, Email: test@example.com, "
            "Phone: 555-867-5309"
        )
        detections = svc.detect_pii(text)
        types_found = {d.pii_type.value for d in detections}
        assert "SSN" in types_found
        assert "EMAIL" in types_found
        assert "PHONE" in types_found

    def test_detect_no_pii(self, svc):
        detections = svc.detect_pii("This is a clean string with no PII.")
        assert len(detections) == 0

    def test_detect_empty_string(self, svc):
        assert svc.detect_pii("") == []

    def test_detect_none(self, svc):
        assert svc.detect_pii(None) == []


# =========================================================================
# PII Redaction
# =========================================================================

@pytest.mark.unit
class TestPIIRedaction:

    def test_redact_ssn(self, svc):
        result = svc.redact_pii("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[REDACTED-SSN]" in result

    def test_redact_email(self, svc):
        result = svc.redact_pii("Email: borrower@example.com")
        assert "borrower@example.com" not in result
        assert "[REDACTED-EMAIL]" in result

    def test_redact_preserves_non_pii(self, svc):
        result = svc.redact_pii("Name: John, SSN: 123-45-6789, City: Denver")
        assert "John" in result
        assert "Denver" in result
        assert "123-45-6789" not in result

    def test_redact_empty_returns_empty(self, svc):
        assert svc.redact_pii("") == ""

    def test_redact_none_returns_none(self, svc):
        assert svc.redact_pii(None) is None

    def test_redact_no_pii_unchanged(self, svc):
        text = "This text has no PII at all"
        assert svc.redact_pii(text) == text


# =========================================================================
# Dict-Level Encrypt / Decrypt
# =========================================================================

@pytest.mark.unit
class TestDictEncryption:

    def test_encrypt_dict_fields(self, svc):
        data = {"ssn": "123-45-6789", "name": "John", "account": "12345678"}
        result = svc.encrypt_dict_fields(data, ["ssn", "account"])
        assert result["ssn"] != "123-45-6789"
        assert result["account"] != "12345678"
        assert result["name"] == "John"  # Untouched

    def test_decrypt_dict_fields(self, svc):
        data = {"ssn": "123-45-6789", "name": "John"}
        encrypted = svc.encrypt_dict_fields(data, ["ssn"])
        decrypted = svc.decrypt_dict_fields(encrypted, ["ssn"])
        assert decrypted["ssn"] == "123-45-6789"
        assert decrypted["name"] == "John"

    def test_dict_fields_none_values(self, svc):
        data = {"ssn": None, "name": "John"}
        result = svc.encrypt_dict_fields(data, ["ssn"])
        assert result["ssn"] is None

    def test_dict_fields_missing_key(self, svc):
        data = {"name": "John"}
        result = svc.encrypt_dict_fields(data, ["ssn"])
        assert "ssn" not in result
        assert result["name"] == "John"

    def test_encrypt_dict_does_not_mutate_original(self, svc):
        data = {"ssn": "123-45-6789"}
        _ = svc.encrypt_dict_fields(data, ["ssn"])
        assert data["ssn"] == "123-45-6789"  # Original unchanged


# =========================================================================
# Log Filter
# =========================================================================

@pytest.mark.unit
class TestSmartDocsPIILogFilter:

    def test_ssn_redacted_from_log(self):
        from services.smart_docs.pii_log_filter import SmartDocsPIIFilter

        pii_filter = SmartDocsPIIFilter()
        record = logging.LogRecord(
            name="services.smart_docs.ocr",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Extracted SSN: 123-45-6789 from document",
            args=(),
            exc_info=None,
        )
        pii_filter.filter(record)
        assert "123-45" not in record.msg
        assert "6789" in record.msg  # Last 4 preserved in masked form

    def test_account_redacted_from_log(self):
        from services.smart_docs.pii_log_filter import SmartDocsPIIFilter

        pii_filter = SmartDocsPIIFilter()
        record = logging.LogRecord(
            name="services.smart_docs.extraction",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Account 1234567890123 found in bank statement",
            args=(),
            exc_info=None,
        )
        pii_filter.filter(record)
        assert "1234567890123" not in record.msg
        assert "ACCT_REDACTED" in record.msg

    def test_email_redacted_from_log(self):
        from services.smart_docs.pii_log_filter import SmartDocsPIIFilter

        pii_filter = SmartDocsPIIFilter()
        record = logging.LogRecord(
            name="services.smart_docs",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing document for user@example.com",
            args=(),
            exc_info=None,
        )
        pii_filter.filter(record)
        assert "user@example.com" not in record.msg
        assert "EMAIL_REDACTED" in record.msg

    def test_ip_address_redacted_from_log(self):
        from services.smart_docs.pii_log_filter import SmartDocsPIIFilter

        pii_filter = SmartDocsPIIFilter()
        record = logging.LogRecord(
            name="services.smart_docs",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Upload from 192.168.1.42",
            args=(),
            exc_info=None,
        )
        pii_filter.filter(record)
        assert "192.168.1.42" not in record.msg
        assert "IP_REDACTED" in record.msg

    def test_clean_message_passes_through(self):
        from services.smart_docs.pii_log_filter import SmartDocsPIIFilter

        pii_filter = SmartDocsPIIFilter()
        record = logging.LogRecord(
            name="services.smart_docs",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Document uploaded successfully for loan 12345",
            args=(),
            exc_info=None,
        )
        pii_filter.filter(record)
        assert record.msg == "Document uploaded successfully for loan 12345"


# =========================================================================
# Missing Encryption Key
# =========================================================================

@pytest.mark.unit
class TestMissingKey:

    def test_missing_key_raises_runtime_error(self, monkeypatch):
        if not HAS_CRYPTO:
            pytest.skip("cryptography library not installed")

        monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)

        from services.smart_docs.pii_encryption_service import PIIEncryptionService

        with pytest.raises(RuntimeError, match="PII_ENCRYPTION_KEY"):
            PIIEncryptionService()

    def test_invalid_key_raises_runtime_error(self, monkeypatch):
        if not HAS_CRYPTO:
            pytest.skip("cryptography library not installed")

        monkeypatch.setenv("PII_ENCRYPTION_KEY", "not-a-valid-fernet-key")

        from services.smart_docs.pii_encryption_service import PIIEncryptionService

        with pytest.raises(RuntimeError, match="Invalid PII_ENCRYPTION_KEY"):
            PIIEncryptionService()


# =========================================================================
# Encrypted Data Not Readable Without Key
# =========================================================================

@pytest.mark.unit
class TestKeyIsolation:

    def test_wrong_key_cannot_decrypt(self, monkeypatch):
        if not HAS_CRYPTO:
            pytest.skip("cryptography library not installed")

        from services.smart_docs.pii_encryption_service import PIIEncryptionService

        # Encrypt with key A
        key_a = _generate_key()
        monkeypatch.setenv("PII_ENCRYPTION_KEY", key_a)
        svc_a = PIIEncryptionService()
        encrypted = svc_a.encrypt("123-45-6789")

        # Attempt decrypt with key B
        key_b = _generate_key()
        monkeypatch.setenv("PII_ENCRYPTION_KEY", key_b)
        from services.smart_docs.pii_encryption_service import reset_pii_encryption_service
        reset_pii_encryption_service()
        svc_b = PIIEncryptionService()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            svc_b.decrypt(encrypted)

    def test_encrypted_value_looks_random(self, svc):
        """Two encryptions of the same plaintext produce different ciphertext (Fernet uses random IV)."""
        ct1 = svc.encrypt("123-45-6789")
        ct2 = svc.encrypt("123-45-6789")
        assert ct1 != ct2, "Fernet should produce different ciphertext each time"
        # But both decrypt to the same value
        assert svc.decrypt(ct1) == svc.decrypt(ct2) == "123-45-6789"


# =========================================================================
# Plaintext Fallback (no cryptography library)
# =========================================================================

@pytest.mark.unit
class TestPlaintextFallback:
    """Test behavior when cryptography is not installed.

    Since the library IS installed in the test environment, we monkeypatch
    the HAS_CRYPTOGRAPHY flag to simulate its absence.
    """

    def test_fallback_encrypt_returns_plaintext(self, monkeypatch):
        import services.smart_docs.pii_encryption_service as mod

        monkeypatch.setattr(mod, "HAS_CRYPTOGRAPHY", False)
        monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)

        svc = mod.PIIEncryptionService()
        assert svc.encrypt("secret") == "secret"

    def test_fallback_decrypt_returns_plaintext(self, monkeypatch):
        import services.smart_docs.pii_encryption_service as mod

        monkeypatch.setattr(mod, "HAS_CRYPTOGRAPHY", False)
        monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)

        svc = mod.PIIEncryptionService()
        assert svc.decrypt("secret") == "secret"
