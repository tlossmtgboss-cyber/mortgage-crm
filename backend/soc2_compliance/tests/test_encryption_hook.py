"""
Tests for SOC 2 Encryption Hook utility.
Coverage: Encrypt/decrypt PII fields, non-PII passthrough, singleton service.
"""
import pytest
from unittest.mock import patch, MagicMock

from soc2_compliance.services.encryption_hook import (
    encrypt_pii_fields,
    decrypt_pii_fields,
    _get_encryption_service,
)
from soc2_compliance.constants import PII_FIELDS


class TestEncryptPiiFields:
    """Test PII field encryption."""

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_encrypts_pii_fields(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_enc.encrypt.return_value = "ENCRYPTED"
        mock_get_enc.return_value = mock_enc

        result = encrypt_pii_fields({
            "ssn": "123-45-6789",
            "name": "John Doe",
        })
        assert result["ssn"] == "ENCRYPTED"
        assert result["name"] == "John Doe"  # Non-PII unchanged

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_skips_empty_values(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_get_enc.return_value = mock_enc

        result = encrypt_pii_fields({"ssn": "", "name": "John"})
        assert result["ssn"] == ""
        mock_enc.encrypt.assert_not_called()

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_skips_non_string_values(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_get_enc.return_value = mock_enc

        result = encrypt_pii_fields({"income": 75000, "name": "John"})
        assert result["income"] == 75000  # Non-string PII left as-is
        mock_enc.encrypt.assert_not_called()

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_custom_fields(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_enc.encrypt.return_value = "ENCRYPTED"
        mock_get_enc.return_value = mock_enc

        result = encrypt_pii_fields(
            {"custom_field": "sensitive", "other": "safe"},
            fields={"custom_field"},
        )
        assert result["custom_field"] == "ENCRYPTED"
        assert result["other"] == "safe"


class TestDecryptPiiFields:
    """Test PII field decryption."""

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_decrypts_encrypted_fields(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_enc.is_encrypted.return_value = True
        mock_enc.decrypt.return_value = "123-45-6789"
        mock_get_enc.return_value = mock_enc

        result = decrypt_pii_fields({
            "ssn": "ENCRYPTED_VALUE",
            "name": "John Doe",
        })
        assert result["ssn"] == "123-45-6789"
        assert result["name"] == "John Doe"

    @patch("soc2_compliance.services.encryption_hook._get_encryption_service")
    def test_skips_non_encrypted_values(self, mock_get_enc):
        mock_enc = MagicMock()
        mock_enc.is_encrypted.return_value = False
        mock_get_enc.return_value = mock_enc

        result = decrypt_pii_fields({"ssn": "plain-text"})
        assert result["ssn"] == "plain-text"
        mock_enc.decrypt.assert_not_called()
