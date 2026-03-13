"""
PII Encryption Service for Smart Docs V2

Column-level encryption for personally identifiable information in mortgage
documents. Protects SSNs, account numbers, income figures, and other sensitive
data extracted by OCR or AI classification.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256) from the
``cryptography`` library. Fernet handles IV generation, padding, versioning,
and authentication automatically.

Encryption key lifecycle:
    - Key is loaded from PII_ENCRYPTION_KEY environment variable.
    - The env var must contain a valid Fernet key (base64-encoded 32-byte key).
    - Generate with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    - In dev environments where the library is missing, the service logs a
      warning and passes data through unencrypted (plaintext fallback).

Usage:
    from services.smart_docs.pii_encryption_service import (
        PIIEncryptionService,
        get_pii_encryption_service,
    )

    svc = get_pii_encryption_service()
    encrypted = svc.encrypt("123-45-6789")
    plaintext = svc.decrypt(encrypted)
    masked = svc.mask_ssn("123-45-6789")  # "***-**-6789"
    detections = svc.detect_pii("Call me at 555-123-4567, SSN 123-45-6789")
    clean = svc.redact_pii("SSN 123-45-6789")  # "SSN [REDACTED-SSN]"
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: cryptography
# ---------------------------------------------------------------------------

try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    InvalidToken = Exception  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# PII type definitions
# ---------------------------------------------------------------------------

class PIIType(str, Enum):
    """Categories of personally identifiable information."""
    SSN = "SSN"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    DOB = "DOB"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    EIN = "EIN"


@dataclass
class PIIDetection:
    """A single PII occurrence found in text."""
    pii_type: PIIType
    value: str
    start: int
    end: int
    masked: str


# ---------------------------------------------------------------------------
# Compiled detection patterns
# ---------------------------------------------------------------------------

# Order matters: more specific patterns first to avoid partial matches.
_PII_PATTERNS: List[Tuple[PIIType, re.Pattern, str]] = [
    # SSN: 123-45-6789 or 123 45 6789
    (
        PIIType.SSN,
        re.compile(
            r"\b(?!000|666|9\d{2})"  # Invalid SSN prefixes
            r"(\d{3})"
            r"[-\s]?"
            r"(?!00)(\d{2})"
            r"[-\s]?"
            r"(?!0000)(\d{4})\b"
        ),
        "[REDACTED-SSN]",
    ),
    # EIN: 12-3456789
    (
        PIIType.EIN,
        re.compile(r"\b\d{2}-\d{7}\b"),
        "[REDACTED-EIN]",
    ),
    # Email
    (
        PIIType.EMAIL,
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED-EMAIL]",
    ),
    # Phone: (123) 456-7890, 123-456-7890, 123.456.7890, +11234567890
    (
        PIIType.PHONE,
        re.compile(
            r"(?:\+?1[-.\s]?)?"
            r"\(?\d{3}\)?[-.\s]?"
            r"\d{3}[-.\s]?"
            r"\d{4}\b"
        ),
        "[REDACTED-PHONE]",
    ),
    # Bank account number: 8-17 digits preceded by "account" keyword
    (
        PIIType.ACCOUNT_NUMBER,
        re.compile(r"(?i)\baccount[_\s#:]*(\d{8,17})\b"),
        "[REDACTED-ACCOUNT]",
    ),
    # Date of birth: MM/DD/YYYY or YYYY-MM-DD
    (
        PIIType.DOB,
        re.compile(
            r"\b(?:"
            r"(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}"
            r"|"
            r"(?:19|20)\d{2}[/\-](?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])"
            r")\b"
        ),
        "[REDACTED-DOB]",
    ),
]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PIIEncryptionService:
    """Column-level encryption and PII handling for Smart Docs.

    Raises ``RuntimeError`` during ``__init__`` when the ``cryptography``
    library is installed but ``PII_ENCRYPTION_KEY`` is not set.  In
    environments where the library is absent, a plaintext fallback is
    used with a prominent warning.
    """

    def __init__(self) -> None:
        self._fernet: Optional[Any] = None  # Fernet instance or None
        self._plaintext_mode = False

        if not HAS_CRYPTOGRAPHY:
            logger.warning(
                "cryptography library not installed -- PII encryption "
                "disabled (plaintext fallback).  Install with: "
                "pip install cryptography"
            )
            self._plaintext_mode = True
            return

        key = os.environ.get("PII_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "PII_ENCRYPTION_KEY environment variable is required when "
                "the cryptography library is installed.  Generate a key "
                "with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )

        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise RuntimeError(
                f"Invalid PII_ENCRYPTION_KEY: {e}.  Must be a valid "
                "Fernet key (base64-encoded 32-byte key)."
            ) from e

        logger.info("PII encryption service initialised (Fernet mode)")

    # ------------------------------------------------------------------
    # Core encrypt / decrypt
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a base64-encoded ciphertext string.

        In plaintext-fallback mode the value is returned unchanged.
        """
        if self._plaintext_mode:
            return plaintext
        assert self._fernet is not None
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded *ciphertext* string.

        In plaintext-fallback mode the value is returned unchanged.

        Raises ``ValueError`` if decryption fails (bad key or tampered data).
        """
        if self._plaintext_mode:
            return ciphertext
        assert self._fernet is not None
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as e:
            raise ValueError(
                "Failed to decrypt PII field -- key mismatch or corrupted data"
            ) from e

    # ------------------------------------------------------------------
    # None-safe wrappers
    # ------------------------------------------------------------------

    def encrypt_field(self, value: Optional[str]) -> Optional[str]:
        """Encrypt *value* if it is not ``None``."""
        if value is None:
            return None
        return self.encrypt(value)

    def decrypt_field(self, value: Optional[str]) -> Optional[str]:
        """Decrypt *value* if it is not ``None``."""
        if value is None:
            return None
        return self.decrypt(value)

    # ------------------------------------------------------------------
    # Masking helpers
    # ------------------------------------------------------------------

    @staticmethod
    def mask_ssn(ssn: str) -> str:
        """Mask an SSN, keeping only the last 4 digits.

        ``"123-45-6789"`` -> ``"***-**-6789"``
        ``"123456789"``   -> ``"***-**-6789"``
        """
        digits = re.sub(r"[^0-9]", "", ssn)
        if len(digits) < 4:
            return "***-**-****"
        return f"***-**-{digits[-4:]}"

    @staticmethod
    def mask_account(account: str) -> str:
        """Mask an account number, keeping only the last 4 digits.

        ``"12345678"`` -> ``"****5678"``
        """
        digits = re.sub(r"[^0-9]", "", account)
        if len(digits) < 4:
            return "****"
        return f"{'*' * (len(digits) - 4)}{digits[-4:]}"

    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask a phone number, keeping only the last 4 digits.

        ``"(555) 123-4567"`` -> ``"(***) ***-4567"``
        """
        digits = re.sub(r"[^0-9]", "", phone)
        if len(digits) < 4:
            return "(***) ***-****"
        return f"(***) ***-{digits[-4:]}"

    # ------------------------------------------------------------------
    # PII detection
    # ------------------------------------------------------------------

    def detect_pii(self, text: str) -> List[PIIDetection]:
        """Scan *text* for PII patterns and return all detections.

        Each detection includes the PII type, the matched value, the
        character offsets, and a pre-masked version.
        """
        if not text:
            return []

        detections: List[PIIDetection] = []
        consumed: set = set()  # character positions already claimed

        for pii_type, pattern, _redaction_label in _PII_PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                # Skip if this region overlaps with a prior detection
                span = set(range(start, end))
                if span & consumed:
                    continue
                consumed |= span

                value = match.group()
                masked = self._mask_for_type(pii_type, value)
                detections.append(PIIDetection(
                    pii_type=pii_type,
                    value=value,
                    start=start,
                    end=end,
                    masked=masked,
                ))

        # Sort by position for consistent ordering
        detections.sort(key=lambda d: d.start)
        return detections

    def redact_pii(self, text: str) -> str:
        """Replace all detected PII in *text* with redaction tokens.

        Returns the redacted text.  Original text is not modified.
        """
        if not text:
            return text

        detections = self.detect_pii(text)
        if not detections:
            return text

        # Build new string, replacing detections from right to left
        # to preserve offsets.
        result = text
        for det in reversed(detections):
            label = self._redaction_label(det.pii_type)
            result = result[:det.start] + label + result[det.end:]
        return result

    # ------------------------------------------------------------------
    # Dict-level helpers
    # ------------------------------------------------------------------

    def encrypt_dict_fields(
        self, data: dict, fields: List[str]
    ) -> dict:
        """Return a copy of *data* with the specified *fields* encrypted.

        Fields that are ``None`` or missing are left unchanged.
        """
        result = dict(data)
        for field_name in fields:
            if field_name in result and result[field_name] is not None:
                result[field_name] = self.encrypt(str(result[field_name]))
        return result

    def decrypt_dict_fields(
        self, data: dict, fields: List[str]
    ) -> dict:
        """Return a copy of *data* with the specified *fields* decrypted.

        Fields that are ``None`` or missing are left unchanged.
        """
        result = dict(data)
        for field_name in fields:
            if field_name in result and result[field_name] is not None:
                result[field_name] = self.decrypt(str(result[field_name]))
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mask_for_type(pii_type: PIIType, value: str) -> str:
        """Generate a masked representation based on PII type."""
        if pii_type == PIIType.SSN:
            digits = re.sub(r"[^0-9]", "", value)
            return f"***-**-{digits[-4:]}" if len(digits) >= 4 else "***-**-****"
        if pii_type == PIIType.ACCOUNT_NUMBER:
            digits = re.sub(r"[^0-9]", "", value)
            return f"{'*' * max(len(digits) - 4, 4)}{digits[-4:]}" if len(digits) >= 4 else "****"
        if pii_type == PIIType.PHONE:
            digits = re.sub(r"[^0-9]", "", value)
            return f"(***) ***-{digits[-4:]}" if len(digits) >= 4 else "(***) ***-****"
        if pii_type == PIIType.EMAIL:
            parts = value.split("@")
            if len(parts) == 2:
                local = parts[0]
                masked_local = local[0] + "***" if len(local) > 1 else "***"
                return f"{masked_local}@{parts[1]}"
            return "[MASKED-EMAIL]"
        if pii_type == PIIType.DOB:
            return "**/**/****"
        if pii_type == PIIType.EIN:
            return "**-***" + value[-4:] if len(value) >= 4 else "**-*******"
        if pii_type == PIIType.DRIVERS_LICENSE:
            return "DL-****"
        return "****"

    @staticmethod
    def _redaction_label(pii_type: PIIType) -> str:
        """Redaction placeholder for a given PII type."""
        return {
            PIIType.SSN: "[REDACTED-SSN]",
            PIIType.ACCOUNT_NUMBER: "[REDACTED-ACCOUNT]",
            PIIType.PHONE: "[REDACTED-PHONE]",
            PIIType.EMAIL: "[REDACTED-EMAIL]",
            PIIType.DOB: "[REDACTED-DOB]",
            PIIType.EIN: "[REDACTED-EIN]",
            PIIType.DRIVERS_LICENSE: "[REDACTED-DL]",
        }.get(pii_type, "[REDACTED]")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[PIIEncryptionService] = None


def get_pii_encryption_service() -> PIIEncryptionService:
    """Return the module-level ``PIIEncryptionService`` singleton.

    The instance is created lazily on first call.  If the encryption key
    is not set and the cryptography library is installed, this will raise
    ``RuntimeError``.
    """
    global _instance
    if _instance is None:
        _instance = PIIEncryptionService()
    return _instance


def reset_pii_encryption_service() -> None:
    """Reset the singleton (useful in tests)."""
    global _instance
    _instance = None
