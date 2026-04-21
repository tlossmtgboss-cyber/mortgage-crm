"""
02-encryption/pii_encryption.py

Hard-fail PII encryption. Replaces the existing module that silently fell back
to plaintext when PII_ENCRYPTION_KEY was missing.

Finding #6 resolution: encryption MUST be available or the app refuses to boot.
No plaintext fallback, ever. No "degraded mode." If the key is missing, that's
a config error, not a runtime condition to gracefully handle.

Drop-in path: backend/app/security/pii_encryption.py
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# AES-256-GCM: 32-byte key, 12-byte nonce, 16-byte auth tag baked into ciphertext
_KEY_BYTES: Final = 32
_NONCE_BYTES: Final = 12


class PIIEncryptionConfigError(RuntimeError):
    """Raised at import/startup when encryption is unusable. Fatal."""


class PIIDecryptionError(RuntimeError):
    """Raised when a value cannot be decrypted. Fatal for the request."""


@dataclass(frozen=True)
class _Cipher:
    primary: AESGCM
    # Rotation support: old key still decrypts, new key encrypts.
    secondary: AESGCM | None


def _load_key(env_var: str, *, required: bool) -> bytes | None:
    raw = os.environ.get(env_var)
    if not raw:
        if required:
            raise PIIEncryptionConfigError(
                f"{env_var} is not set. PII encryption is mandatory — the app "
                "will not start without it. Set the key in Railway env vars."
            )
        return None

    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as e:
        raise PIIEncryptionConfigError(
            f"{env_var} is not valid urlsafe base64: {e}"
        ) from e

    if len(key) != _KEY_BYTES:
        raise PIIEncryptionConfigError(
            f"{env_var} must decode to exactly {_KEY_BYTES} bytes "
            f"(got {len(key)}). Generate with: "
            f"python -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'"
        )

    return key


@lru_cache(maxsize=1)
def _cipher() -> _Cipher:
    """Build and cache the AESGCM cipher. Raises at first call if misconfigured."""
    primary_key = _load_key("PII_ENCRYPTION_KEY", required=True)
    secondary_key = _load_key("PII_ENCRYPTION_KEY_PREVIOUS", required=False)

    assert primary_key is not None  # _load_key with required=True raises otherwise
    return _Cipher(
        primary=AESGCM(primary_key),
        secondary=AESGCM(secondary_key) if secondary_key else None,
    )


def validate_encryption_at_startup() -> None:
    """
    Call during FastAPI app startup. Forces key load and a round-trip
    encrypt/decrypt so misconfiguration surfaces immediately, not on first
    PII write.
    """
    cipher = _cipher()
    test_plaintext = b"startup-validation"
    blob = _encrypt_bytes(test_plaintext, cipher)
    recovered = _decrypt_bytes(blob, cipher)
    if recovered != test_plaintext:
        raise PIIEncryptionConfigError(
            "Encryption round-trip failed during startup validation"
        )
    logger.info("PII encryption validated at startup (AES-256-GCM)")


def _encrypt_bytes(plaintext: bytes, cipher: _Cipher) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    ct = cipher.primary.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ct


def _decrypt_bytes(blob: bytes, cipher: _Cipher) -> bytes:
    if len(blob) < _NONCE_BYTES + 16:
        raise PIIDecryptionError("Ciphertext too short")
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]

    try:
        return cipher.primary.decrypt(nonce, ct, associated_data=None)
    except InvalidTag:
        if cipher.secondary is not None:
            try:
                return cipher.secondary.decrypt(nonce, ct, associated_data=None)
            except InvalidTag as e:
                raise PIIDecryptionError(
                    "Decryption failed with both current and previous key. "
                    "Either the ciphertext is corrupted or the key has been "
                    "rotated more than once without re-encrypting."
                ) from e
        raise PIIDecryptionError(
            "Decryption failed. Key may have been rotated; set "
            "PII_ENCRYPTION_KEY_PREVIOUS to the prior key during the rotation window."
        )


def encrypt_pii(plaintext: str) -> str:
    """
    Encrypt a UTF-8 string. Returns urlsafe-base64 string suitable for storage
    in a TEXT column. No plaintext fallback.
    """
    if plaintext is None:
        raise ValueError("Cannot encrypt None. Use NULL at the column level instead.")
    blob = _encrypt_bytes(plaintext.encode("utf-8"), _cipher())
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_pii(ciphertext: str) -> str:
    """Decrypt a value produced by encrypt_pii. Raises PIIDecryptionError on failure."""
    if ciphertext is None:
        raise ValueError("Cannot decrypt None")
    try:
        blob = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    except Exception as e:
        raise PIIDecryptionError(f"Not valid urlsafe base64: {e}") from e
    return _decrypt_bytes(blob, _cipher()).decode("utf-8")


# --- SQLAlchemy TypeDecorator for transparent column-level encryption ---

from sqlalchemy import String, TypeDecorator


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy column type that transparently encrypts on write and decrypts
    on read. Use for SSN, DOB, bank account numbers, etc.

    Usage:
        class Borrower(Base):
            ssn: Mapped[str] = mapped_column(EncryptedString(512), nullable=True)
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_pii(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_pii(value)
