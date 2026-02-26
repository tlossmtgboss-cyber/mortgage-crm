"""
Encryption Hook — Reusable PII encrypt/decrypt utilities for route handlers.
SOC 2 Criteria: C1 (Confidentiality), CC5 (Control Activities)

Provides convenience functions for encrypting/decrypting PII fields in
request/response data, using the EncryptionService singleton.
"""
import logging
from typing import Dict, Any, Set, Optional

from ..constants import PII_FIELDS
from .encryption_service import EncryptionService
from ..config import SOC2Config

logger = logging.getLogger("soc2.encryption_hook")

# Module-level singleton
_encryption_service: Optional[EncryptionService] = None


def _get_encryption_service() -> EncryptionService:
    """Get or create the EncryptionService singleton."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService(config=SOC2Config.from_env())
    return _encryption_service


def encrypt_pii_fields(
    data: Dict[str, Any],
    fields: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Encrypt PII fields in a data dictionary.

    Args:
        data: Dictionary of field names to values.
        fields: Set of field names to encrypt. Defaults to PII_FIELDS from constants.

    Returns:
        New dictionary with PII fields encrypted, non-PII fields unchanged.
    """
    target_fields = fields or PII_FIELDS
    enc = _get_encryption_service()
    result = {}

    for key, value in data.items():
        if key.lower() in target_fields and isinstance(value, str) and value:
            try:
                result[key] = enc.encrypt(value)
            except Exception as e:
                logger.error(f"Failed to encrypt field '{key}': {e}")
                result[key] = value
        else:
            result[key] = value

    return result


def decrypt_pii_fields(
    data: Dict[str, Any],
    fields: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Decrypt PII fields in a data dictionary.

    Args:
        data: Dictionary of field names to values.
        fields: Set of field names to decrypt. Defaults to PII_FIELDS from constants.

    Returns:
        New dictionary with PII fields decrypted, non-PII fields unchanged.
    """
    target_fields = fields or PII_FIELDS
    enc = _get_encryption_service()
    result = {}

    for key, value in data.items():
        if key.lower() in target_fields and isinstance(value, str) and value:
            try:
                if enc.is_encrypted(value):
                    result[key] = enc.decrypt(value)
                else:
                    result[key] = value
            except Exception as e:
                logger.error(f"Failed to decrypt field '{key}': {e}")
                result[key] = value
        else:
            result[key] = value

    return result
