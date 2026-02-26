"""
Encryption Service — Field-level encryption for PII data.
SOC 2 Criteria: C1 (Confidentiality), CC5 (Control Activities)

Provides Fernet symmetric encryption for sensitive fields like SSN, bank accounts,
tax IDs, etc. This ensures data is encrypted at rest in PostgreSQL.

IMPORTANT: The encryption key must be stored securely (env var, secrets manager)
and NEVER committed to version control. Key rotation should be performed annually.
"""
import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ..config import SOC2Config

logger = logging.getLogger("soc2.encryption")


class EncryptionService:
    """
    Field-level encryption for PII and sensitive data.
    
    Usage:
        enc = EncryptionService()
        
        # Encrypt before storing
        encrypted_ssn = enc.encrypt("123-45-6789")
        
        # Decrypt when retrieving
        ssn = enc.decrypt(encrypted_ssn)
        
        # Hash for lookups (one-way)
        ssn_hash = enc.hash_value("123-45-6789")
    """

    def __init__(self, config: Optional[SOC2Config] = None):
        self.config = config or SOC2Config.from_env()
        self._fernet = self._init_fernet()

    def _init_fernet(self) -> Optional[Fernet]:
        """Initialize Fernet encryption with the configured key."""
        key = self.config.field_encryption_key
        if not key:
            # In production, encryption MUST be configured
            if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PRODUCTION"):
                raise ValueError(
                    "SOC2_FIELD_ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
            logger.warning(
                "SOC2_FIELD_ENCRYPTION_KEY not set. "
                "Field-level encryption is DISABLED. "
                "Set this variable before production deployment."
            )
            return None
        try:
            return Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            logger.error(f"Invalid encryption key format: {e}")
            raise ValueError(
                "SOC2_FIELD_ENCRYPTION_KEY must be a valid Fernet key. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string. Returns base64-encoded ciphertext.
        
        Raises ValueError if encryption is not configured.
        """
        if not self._fernet:
            raise ValueError(
                "Encryption not configured. Set SOC2_FIELD_ENCRYPTION_KEY."
            )
        if not plaintext:
            return plaintext
        try:
            encrypted = self._fernet.encrypt(plaintext.encode("utf-8"))
            # Fernet.encrypt() already returns URL-safe base64 bytes
            return encrypted.decode("utf-8")
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a base64-encoded ciphertext string.
        
        Raises ValueError if decryption fails (wrong key, corrupted data).
        """
        if not self._fernet:
            raise ValueError(
                "Encryption not configured. Set SOC2_FIELD_ENCRYPTION_KEY."
            )
        if not ciphertext:
            return ciphertext
        try:
            # Fernet tokens are already URL-safe base64 — decrypt directly
            decrypted = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken:
            logger.error("Decryption failed — invalid token. Possible key mismatch or data corruption.")
            raise ValueError("Decryption failed. Check encryption key.")
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise

    def hash_value(self, value: str, salt: Optional[str] = None) -> str:
        """
        One-way hash for lookups (e.g., searching by SSN without decrypting all records).
        Uses SHA-256 with an optional salt.
        """
        if not value:
            return value
        salt = salt or os.getenv("SOC2_HASH_SALT", "")
        if not salt:
            raise ValueError(
                "SOC2_HASH_SALT environment variable must be set for secure hashing."
            )
        return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()

    def mask_value(self, value: str, visible_chars: int = 4) -> str:
        """
        Mask a sensitive value for display purposes.
        Shows only the last N characters.
        
        Example: mask_value("123-45-6789", 4) → "***6789"
        """
        if not value or len(value) <= visible_chars:
            return "****"
        return f"***{value[-visible_chars:]}"

    def is_encrypted(self, value: str) -> bool:
        """
        Heuristic check if a value appears to be encrypted (base64 + Fernet structure).
        Useful for migration scripts to avoid double-encryption.
        """
        if not value or len(value) < 50:
            return False
        try:
            decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
            # Fernet tokens start with version byte 0x80
            return decoded[0:1] == b'\x80'
        except Exception:
            return False

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key."""
        return Fernet.generate_key().decode("utf-8")
