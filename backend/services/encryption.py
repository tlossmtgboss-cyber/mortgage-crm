"""
Field-level encryption for PII data at rest.

Provides a FieldEncryptor class that derives a Fernet key from an application
secret via PBKDF2, and an EncryptedString SQLAlchemy TypeDecorator for
transparent encrypt/decrypt on model columns.

Intended for CCPA/SOC2 compliance on fields like attendee_email, attendee_phone.

Usage:
    from services.encryption import EncryptedString, FieldEncryptor

    # In a model:
    attendee_email = Column(EncryptedString(500))

    # Manual usage:
    encryptor = FieldEncryptor.get_instance()
    ciphertext = encryptor.encrypt("user@example.com")
    plaintext = encryptor.decrypt(ciphertext)
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# Static salt for PBKDF2 key derivation.  In a full key-management setup this
# would be stored alongside (but separate from) the key material.  Using a
# fixed application-level salt is acceptable when the input key already has
# reasonable entropy (e.g. a 32+ char SECRET_KEY).
_KDF_SALT = b"perennia-pii-salt-v1"
_KDF_ITERATIONS = 100_000


class FieldEncryptor:
    """Encrypts/decrypts individual field values for at-rest PII protection.

    Derives a 256-bit Fernet key from the application secret using PBKDF2-SHA256
    so the secret does not need to be a valid Fernet key itself.

    Thread-safe after construction; Fernet is safe for concurrent use.
    """

    _instance: Optional["FieldEncryptor"] = None

    def __init__(self, encryption_key: Optional[str] = None):
        key = encryption_key or os.getenv("ENCRYPTION_KEY") or os.getenv("SECRET_KEY")
        if not key:
            raise ValueError(
                "ENCRYPTION_KEY or SECRET_KEY environment variable must be set "
                "for field-level encryption"
            )
        # Derive a proper 32-byte Fernet key from the application secret
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_KDF_SALT,
            iterations=_KDF_ITERATIONS,
        )
        derived = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        self.fernet = Fernet(derived)

    # ------------------------------------------------------------------
    # Core encrypt / decrypt
    # ------------------------------------------------------------------

    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext string.  Returns a Fernet token (URL-safe base64)."""
        if not value:
            return value
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        """Decrypt a Fernet token back to plaintext.

        If the value does not look like a valid Fernet token (e.g. legacy
        unencrypted data), it is returned as-is so that pre-existing rows
        continue to work before the migration script runs.
        """
        if not value:
            return value
        try:
            return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, Exception):
            # Value is not a valid Fernet token — likely legacy plaintext.
            # Log at debug level to avoid noise during migration window.
            logger.debug(
                "Decryption returned original value (likely unencrypted legacy data)"
            )
            return value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_encrypted(value: str) -> bool:
        """Heuristic check whether a value is already a Fernet token.

        Fernet tokens are URL-safe base64 strings that decode to bytes whose
        first byte is the version marker 0x80.  Plaintext emails/phones will
        never match this pattern.
        """
        if not value or len(value) < 50:
            return False
        try:
            decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
            return decoded[0:1] == b"\x80"
        except Exception as _exc:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "FieldEncryptor":
        """Return the module-level singleton, creating it on first access."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (useful for testing with different keys)."""
        cls._instance = None


# ======================================================================
# SQLAlchemy TypeDecorator
# ======================================================================


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts on write and
    decrypts on read.

    The underlying database column is a plain VARCHAR — encrypted Fernet
    tokens are longer than the original plaintext, so size the column
    accordingly (e.g. 500 for a 255-char email).

    Example::

        class Appointment(Base):
            attendee_email = Column(EncryptedString(500))
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt before INSERT/UPDATE."""
        if value is not None:
            return FieldEncryptor.get_instance().encrypt(value)
        return value

    def process_result_value(self, value, dialect):
        """Decrypt after SELECT.  Legacy plaintext is returned unchanged."""
        if value is not None:
            return FieldEncryptor.get_instance().decrypt(value)
        return value
